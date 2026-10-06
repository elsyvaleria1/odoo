use std::collections::{HashMap, HashSet};

use pyo3::exceptions::{PyIndexError, PyOverflowError};
use pyo3::prelude::*;
use pyo3::types::{PyList, PyTuple};

type FieldId = u32;
type Bucket = (Vec<FieldId>, Vec<FieldId>);
type FieldTriggers = (FieldId, Vec<Bucket>);
type Meta = (bool, bool, u32, u32, u32, u32, u32);

#[derive(Clone, Copy)]
struct FieldMeta {
    is_many2one: bool,
    is_one2many: bool,
    name: u32,
    inverse_name: u32,
    model_name: u32,
    comodel_name: u32,
    // The stored column the field stands for. Every model of a table-
    // inheritance tree keeps its own field for one column, so a cycle closes
    // on the fact, or a self-dependency shared by n siblings costs n! paths.
    fact: u32,
}

struct Graph {
    triggers: HashMap<FieldId, Vec<Bucket>>,
    meta: Vec<FieldMeta>,
    // The component of each fact in the graph of descents, facts renumbered
    // densely so the walk's per-fact state is a vector.
    component: Vec<u32>,
    components: usize,
}

impl Graph {
    fn new(triggers: HashMap<FieldId, Vec<Bucket>>, mut meta: Vec<FieldMeta>) -> Self {
        let mut dense: HashMap<u32, u32> = HashMap::new();
        for m in &mut meta {
            let next = dense.len() as u32;
            m.fact = *dense.entry(m.fact).or_insert(next);
        }
        let (component, components) = components(&triggers, &meta, dense.len());
        Self {
            triggers,
            meta,
            component,
            components,
        }
    }

    fn cancels(&self, f1: FieldId, f2: FieldId) -> bool {
        let (a, b) = (self.meta[f1 as usize], self.meta[f2 as usize]);
        a.is_many2one
            && b.is_one2many
            && b.inverse_name == a.name
            && a.model_name == b.comodel_name
            && a.comodel_name == b.model_name
    }

    fn fact(&self, field: FieldId) -> usize {
        self.meta[field as usize].fact as usize
    }
}

fn components(
    triggers: &HashMap<FieldId, Vec<Bucket>>,
    meta: &[FieldMeta],
    facts: usize,
) -> (Vec<u32>, usize) {
    let fact = |f: FieldId| meta[f as usize].fact as usize;
    let mut successors: Vec<Vec<usize>> = vec![Vec::new(); facts];
    for (&dep, buckets) in triggers {
        let out = &mut successors[fact(dep)];
        for (_, targets) in buckets {
            out.extend(
                targets
                    .iter()
                    .filter(|t| triggers.contains_key(t))
                    .map(|&t| fact(t)),
            );
        }
    }
    const UNSEEN: usize = usize::MAX;
    let mut index = vec![UNSEEN; facts];
    let mut low = vec![0; facts];
    let mut on_pending = vec![false; facts];
    let mut component = vec![0u32; facts];
    let mut components = 0;
    let mut pending = Vec::new();
    let mut work: Vec<(usize, usize)> = Vec::new();
    let mut next = 0;
    for start in 0..facts {
        if index[start] != UNSEEN {
            continue;
        }
        index[start] = next;
        low[start] = next;
        next += 1;
        pending.push(start);
        on_pending[start] = true;
        work.push((start, 0));
        while let Some(top) = work.last_mut() {
            let node = top.0;
            if let Some(&succ) = successors[node].get(top.1) {
                top.1 += 1;
                if index[succ] == UNSEEN {
                    index[succ] = next;
                    low[succ] = next;
                    next += 1;
                    pending.push(succ);
                    on_pending[succ] = true;
                    work.push((succ, 0));
                } else if on_pending[succ] {
                    low[node] = low[node].min(index[succ]);
                }
                continue;
            }
            work.pop();
            if let Some(&(parent, _)) = work.last() {
                low[parent] = low[parent].min(low[node]);
            }
            if low[node] == index[node] {
                loop {
                    let member = pending.pop().expect("a component's root is pending");
                    on_pending[member] = false;
                    component[member] = components as u32;
                    if member == node {
                        break;
                    }
                }
                components += 1;
            }
        }
    }
    (component, components)
}

// Per-worker state that every walk leaves as it found it: a fact is on the
// stack at most once, and each frame pushed is popped.
struct Scratch {
    on_stack: Vec<bool>,
    active: Vec<u32>,
}

impl Scratch {
    fn new(graph: &Graph) -> Self {
        Self {
            on_stack: vec![false; graph.component.len()],
            active: vec![0; graph.components],
        }
    }
}

struct Node {
    root: Vec<FieldId>,
    children: Vec<(FieldId, usize)>,
    parent: usize,
    label: FieldId,
}

// A trie of paths that is the tree itself: a child always comes after its
// parent, so neither building the Python value nor dropping the tree recurses
// on its depth.
struct Tree {
    nodes: Vec<Node>,
    child_of: HashMap<(usize, FieldId), usize>,
    listed: HashSet<(usize, FieldId)>,
}

impl Tree {
    fn new() -> Self {
        Self {
            nodes: vec![Node {
                root: Vec::new(),
                children: Vec::new(),
                parent: 0,
                label: 0,
            }],
            child_of: HashMap::new(),
            listed: HashSet::new(),
        }
    }

    fn descend(&mut self, graph: &Graph, mut node: usize, path: &[FieldId]) -> usize {
        let mut start = 0;
        while node != 0 && start < path.len() && graph.cancels(self.nodes[node].label, path[start])
        {
            node = self.nodes[node].parent;
            start += 1;
        }
        for &label in &path[start..] {
            node = match self.child_of.get(&(node, label)) {
                Some(&child) => child,
                None => {
                    let child = self.nodes.len();
                    self.nodes.push(Node {
                        root: Vec::new(),
                        children: Vec::new(),
                        parent: node,
                        label,
                    });
                    self.nodes[node].children.push((label, child));
                    self.child_of.insert((node, label), child);
                    child
                }
            };
        }
        node
    }

    fn list(&mut self, node: usize, targets: &[FieldId]) {
        for &target in targets {
            if self.listed.insert((node, target)) {
                self.nodes[node].root.push(target);
            }
        }
    }

    fn to_py<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let mut built: Vec<Option<Bound<'py, PyTuple>>> = vec![None; self.nodes.len()];
        for (index, node) in self.nodes.iter().enumerate().rev() {
            let root = PyList::new(py, &node.root)?;
            let mut children = Vec::with_capacity(node.children.len());
            for &(label, child) in &node.children {
                let subtree = built[child]
                    .take()
                    .expect("a child is built before its parent");
                children.push((label, subtree));
            }
            let children = PyList::new(py, children)?;
            built[index] = Some(PyTuple::new(py, [root.into_any(), children.into_any()])?);
        }
        Ok(built[0].take().expect("the arena holds its root"))
    }
}

struct Frame {
    field: FieldId,
    prefix: usize,
    node: usize,
    fact: usize,
    component: usize,
    bucket: usize,
    target: usize,
}

fn enter(graph: &Graph, scratch: &mut Scratch, field: FieldId, prefix: usize) -> Frame {
    let fact = graph.fact(field);
    let component = graph.component[fact] as usize;
    scratch.on_stack[fact] = true;
    scratch.active[component] += 1;
    Frame {
        field,
        prefix,
        node: prefix,
        fact,
        component,
        bucket: 0,
        target: 0,
    }
}

// An explicit stack, not recursion: a dependency chain is as deep as the
// registry makes it, and the walk may run on a 2 MiB worker thread.
fn tree_of(graph: &Graph, scratch: &mut Scratch, field: FieldId) -> Tree {
    let mut tree = Tree::new();
    if !graph.triggers.contains_key(&field) {
        return tree;
    }
    let mut expanded: HashSet<(FieldId, usize)> = HashSet::new();
    let mut stack = vec![enter(graph, scratch, field, 0)];
    while let Some(frame) = stack.last_mut() {
        let buckets = &graph.triggers[&frame.field];
        let Some((path, targets)) = buckets.get(frame.bucket) else {
            let done = stack.pop().expect("the loop holds a frame");
            scratch.on_stack[done.fact] = false;
            scratch.active[done.component] -= 1;
            continue;
        };
        if frame.target == 0 {
            frame.node = tree.descend(graph, frame.prefix, path);
            tree.list(frame.node, targets);
        }
        let mut descend = None;
        while let Some(&target) = targets.get(frame.target) {
            frame.target += 1;
            let fact = graph.fact(target);
            if scratch.on_stack[fact] || !graph.triggers.contains_key(&target) {
                continue;
            }
            // With no frame of its component on the stack, nothing the walk
            // below `target` reaches is on the stack either, so its result
            // depends on (target, node) alone and is already in.
            if scratch.active[graph.component[fact] as usize] == 0
                && !expanded.insert((target, frame.node))
            {
                continue;
            }
            descend = Some((target, frame.node));
            break;
        }
        match descend {
            Some((target, node)) => {
                let child = enter(graph, scratch, target, node);
                stack.push(child);
            }
            None => {
                frame.bucket += 1;
                frame.target = 0;
            }
        }
    }
    tree
}

fn trees_of(graph: &Graph, fields: &[FieldId]) -> Vec<Tree> {
    let workers = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .min(fields.len().max(1));
    let build = |part: &[FieldId]| {
        let mut scratch = Scratch::new(graph);
        part.iter()
            .map(|&f| tree_of(graph, &mut scratch, f))
            .collect::<Vec<_>>()
    };
    if workers <= 1 || fields.len() < 64 {
        return build(fields);
    }
    let chunk = fields.len().div_ceil(workers);
    std::thread::scope(|scope| {
        let handles: Vec<_> = fields
            .chunks(chunk)
            .map(|part| scope.spawn(move || build(part)))
            .collect();
        handles
            .into_iter()
            .flat_map(|h| h.join().expect("trigger tree worker panicked"))
            .collect()
    })
}

const OUT_OF_RANGE: &str = "get_trigger_trees: a field id is out of range of `meta`";

// A negative or oversized id is out of range like any other, not an
// OverflowError from the integer conversion: the pure-Python twin says so too.
#[repr(transparent)]
pub(crate) struct FieldIdArg(FieldId);

impl<'a, 'py> FromPyObject<'a, 'py> for FieldIdArg {
    type Error = PyErr;

    fn extract(obj: Borrowed<'a, 'py, PyAny>) -> PyResult<Self> {
        match obj.extract::<FieldId>() {
            Ok(id) => Ok(Self(id)),
            Err(err) if err.is_instance_of::<PyOverflowError>(obj.py()) => {
                Err(PyIndexError::new_err(OUT_OF_RANGE))
            }
            Err(err) => Err(err),
        }
    }
}

fn ids(args: Vec<FieldIdArg>) -> Vec<FieldId> {
    args.into_iter().map(|FieldIdArg(id)| id).collect()
}

type BucketArg = (Vec<FieldIdArg>, Vec<FieldIdArg>);

#[pyfunction]
#[pyo3(signature = (triggers, meta, fields=None))]
pub fn get_trigger_trees<'py>(
    py: Python<'py>,
    triggers: Vec<(FieldIdArg, Vec<BucketArg>)>,
    meta: Vec<Meta>,
    fields: Option<Vec<FieldIdArg>>,
) -> PyResult<Bound<'py, PyList>> {
    let triggers: Vec<FieldTriggers> = triggers
        .into_iter()
        .map(|(FieldIdArg(dep), buckets)| {
            let buckets = buckets
                .into_iter()
                .map(|(path, targets)| (ids(path), ids(targets)))
                .collect();
            (dep, buckets)
        })
        .collect();
    let in_range = |f: FieldId| (f as usize) < meta.len();
    let all_in_range = triggers.iter().all(|(dep, buckets)| {
        in_range(*dep)
            && buckets
                .iter()
                .all(|(path, targets)| path.iter().chain(targets).all(|&f| in_range(f)))
    }) && fields.iter().flatten().all(|&FieldIdArg(f)| in_range(f));
    if !all_in_range {
        return Err(PyIndexError::new_err(OUT_OF_RANGE));
    }
    let fields: Vec<FieldId> = match fields {
        Some(fields) => ids(fields),
        None => {
            let mut declared = HashSet::with_capacity(triggers.len());
            triggers
                .iter()
                .map(|(dep, _)| *dep)
                .filter(|dep| declared.insert(*dep))
                .collect()
        }
    };
    let triggers: HashMap<FieldId, Vec<Bucket>> = triggers.into_iter().collect();
    let meta: Vec<FieldMeta> = meta
        .into_iter()
        .map(|(m, o, n, i, mo, co, fact)| FieldMeta {
            is_many2one: m,
            is_one2many: o,
            name: n,
            inverse_name: i,
            model_name: mo,
            comodel_name: co,
            fact,
        })
        .collect();
    let trees = py.detach(|| trees_of(&Graph::new(triggers, meta), &fields));
    PyList::new(
        py,
        fields
            .iter()
            .zip(&trees)
            .map(|(field, tree)| -> PyResult<_> { Ok((*field, tree.to_py(py)?)) })
            .collect::<PyResult<Vec<_>>>()?,
    )
}

#[cfg(test)]
mod tests {
    use super::{Bucket, FieldMeta, Graph, Scratch, Tree, tree_of};
    use std::collections::HashMap;

    fn plain(m2o: bool, o2m: bool, name: u32, inverse: u32, model: u32, comodel: u32) -> FieldMeta {
        FieldMeta {
            is_many2one: m2o,
            is_one2many: o2m,
            name,
            inverse_name: inverse,
            model_name: model,
            comodel_name: comodel,
            fact: u32::MAX,
        }
    }

    // a field left with no fact is its own fact
    fn graph(edges: &[(u32, &[u32], &[u32])], meta: Vec<FieldMeta>) -> Graph {
        let mut triggers: HashMap<u32, Vec<Bucket>> = HashMap::new();
        for (dep, path, targets) in edges {
            triggers
                .entry(*dep)
                .or_default()
                .push((path.to_vec(), targets.to_vec()));
        }
        let meta = meta
            .into_iter()
            .enumerate()
            .map(|(i, m)| FieldMeta {
                fact: if m.fact == u32::MAX { i as u32 } else { m.fact },
                ..m
            })
            .collect();
        Graph::new(triggers, meta)
    }

    fn tree(graph: &Graph, field: u32) -> Tree {
        tree_of(graph, &mut Scratch::new(graph), field)
    }

    fn count(tree: &Tree) -> usize {
        tree.nodes.len()
    }

    #[test]
    fn siblings_sharing_one_fact_close_the_cycle_once_and_list_every_sibling() {
        // n copies F_i of one column (fact 0), each depending on itself through
        // its own many2one P_i (facts 1): F_i --[P_j]--> F_j for every i, j.
        let n = 9u32;
        let mut meta: Vec<FieldMeta> = (0..n).map(|_| plain(false, false, 0, 0, 0, 0)).collect();
        meta.iter_mut().for_each(|m| m.fact = 0);
        meta.extend((0..n).map(|i| FieldMeta {
            fact: 1,
            ..plain(true, false, 1, 0, i, i)
        }));
        let edges: Vec<(u32, Vec<u32>, Vec<u32>)> = (0..n)
            .flat_map(|i| (0..n).map(move |j| (i, vec![n + j], vec![j])))
            .collect();
        let borrowed: Vec<(u32, &[u32], &[u32])> = edges
            .iter()
            .map(|(d, p, t)| (*d, p.as_slice(), t.as_slice()))
            .collect();
        let g = graph(&borrowed, meta);
        let tree = tree(&g, 0);
        assert_eq!(count(&tree), 1 + n as usize);
        let listed: Vec<u32> = flat(&tree)
            .into_iter()
            .flat_map(|(_, roots)| roots)
            .collect();
        assert_eq!(listed, (0..n).collect::<Vec<_>>());
    }

    fn flat(tree: &Tree) -> Vec<(Vec<u32>, Vec<u32>)> {
        let mut out = Vec::new();
        let mut stack = vec![(Vec::new(), 0)];
        while let Some((prefix, index)) = stack.pop() {
            let node = &tree.nodes[index];
            out.push((prefix.clone(), node.root.clone()));
            for &(label, child) in node.children.iter().rev() {
                let mut path = prefix.clone();
                path.push(label);
                stack.push((path, child));
            }
        }
        out
    }

    fn chain(depth: u32, label: Option<u32>) -> Graph {
        let meta = (0..=depth.max(label.unwrap_or(0)))
            .map(|_| plain(false, false, 0, 0, 0, 0))
            .collect();
        let path: Vec<u32> = label.into_iter().collect();
        let edges: Vec<(u32, &[u32], Vec<u32>)> = (0..depth)
            .map(|i| (i, path.as_slice(), vec![i + 1]))
            .collect();
        let borrowed: Vec<(u32, &[u32], &[u32])> = edges
            .iter()
            .map(|(d, p, t)| (*d, *p, t.as_slice()))
            .collect();
        graph(&borrowed, meta)
    }

    fn on_a_small_stack<T: Send + 'static>(walk: impl FnOnce() -> T + Send + 'static) -> T {
        std::thread::Builder::new()
            .stack_size(64 * 1024)
            .spawn(walk)
            .unwrap()
            .join()
            .unwrap()
    }

    #[test]
    fn a_chain_deeper_than_the_stack_is_walked_without_recursing() {
        let depth = 4000;
        let flattened = on_a_small_stack(move || flat(&tree(&chain(depth, None), 0)));
        assert_eq!(flattened, [(vec![], (1..=depth).collect::<Vec<_>>())]);
    }

    #[test]
    fn a_labelled_chain_opens_one_level_per_link_and_drops_flat() {
        let depth = 4000;
        let nodes = on_a_small_stack(move || count(&tree(&chain(depth, Some(depth)), 0)));
        assert_eq!(nodes, 1 + depth as usize);
    }

    #[test]
    fn a_chain_collects_every_descendant_into_the_root_in_order() {
        let meta = (0..4).map(|_| plain(false, false, 0, 0, 0, 0)).collect();
        let g = graph(&[(0, &[], &[1]), (1, &[], &[2]), (2, &[], &[3])], meta);
        assert_eq!(flat(&tree(&g, 0)), [(vec![], vec![1, 2, 3])]);
    }

    #[test]
    fn a_labelled_path_opens_a_subtree_and_a_diamond_dedups_its_root() {
        let meta = (0..5).map(|_| plain(false, false, 0, 0, 0, 0)).collect();
        let g = graph(&[(0, &[], &[1, 2]), (1, &[4], &[3]), (2, &[4], &[3])], meta);
        assert_eq!(
            flat(&tree(&g, 0)),
            [(vec![], vec![1, 2]), (vec![4], vec![3])]
        );
    }

    #[test]
    fn a_many2one_followed_by_its_inverse_one2many_cancels_out() {
        // field 1: many2one named n=1 on model A(=0) to B(=1); field 2: one2many on B to A with inverse n=1
        let meta = vec![
            plain(false, false, 0, 0, 0, 0),
            plain(true, false, 1, 0, 0, 1),
            plain(false, true, 0, 1, 1, 0),
            plain(false, false, 0, 0, 0, 0),
        ];
        let g = graph(&[(0, &[1], &[3]), (3, &[2], &[0])], meta);
        let mut trie = Tree::new();
        let through_1 = trie.descend(&g, 0, &[1]);
        assert_eq!(trie.descend(&g, through_1, &[2]), 0);
        assert_eq!(
            trie.descend(&g, through_1, &[1]),
            trie.descend(&g, 0, &[1, 1])
        );
        let tree = tree(&g, 0);
        assert_eq!(flat(&tree), [(vec![], vec![0]), (vec![1], vec![3])]);
    }

    #[test]
    fn a_cycle_terminates_and_still_lists_every_member_once() {
        let meta = (0..3).map(|_| plain(false, false, 0, 0, 0, 0)).collect();
        let g = graph(&[(0, &[], &[1]), (1, &[], &[2]), (2, &[], &[0])], meta);
        assert_eq!(flat(&tree(&g, 0)), [(vec![], vec![1, 2, 0])]);
    }

    #[test]
    fn a_field_with_no_triggers_is_an_empty_tree() {
        let g = graph(&[], vec![plain(false, false, 0, 0, 0, 0)]);
        assert_eq!(flat(&tree(&g, 0)), [(vec![], vec![])]);
    }
}
