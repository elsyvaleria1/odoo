use std::sync::Arc;

use pyo3::prelude::*;

use super::lines::LineCursor;
use super::walk::scan_files;

type ByteMatch = (String, usize, usize);

#[pyfunction]
pub fn scan_byte_patterns(
    py: Python<'_>,
    roots: Vec<String>,
    extensions: Vec<String>,
    patterns: Vec<Vec<u8>>,
    exclude_dirs: Vec<String>,
) -> PyResult<Vec<ByteMatch>> {
    if patterns.iter().any(Vec::is_empty) {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "scan_byte_patterns: patterns must not be empty",
        ));
    }
    let pats: Arc<[Vec<u8>]> = patterns.into();

    scan_files(
        py,
        &roots,
        &extensions,
        exclude_dirs,
        move |path, content, hits| {
            let path_str = path.to_string_lossy().into_owned();
            let (found, _scanned) = byte_hits(content, &pats);
            hits.extend(
                found
                    .into_iter()
                    .map(|(line, idx)| (path_str.clone(), line, idx)),
            );
        },
    )
}

fn byte_hits(content: &[u8], pats: &[Vec<u8>]) -> (Vec<(usize, usize)>, usize) {
    let mut lines = LineCursor::new(content);
    let mut found = Vec::new();
    for (idx, pat) in pats.iter().enumerate() {
        let mut start = 0;
        let mut last_line = 0;
        lines.restart();
        while let Some(pos) = memchr::memmem::find(&content[start..], pat) {
            let abs = start + pos;
            let line = lines.line_of(abs);

            if line != last_line {
                found.push((line, idx));
                last_line = line;
            }

            start = abs + pat.len();
        }
    }
    (found, lines.scanned())
}

#[pyfunction]
pub fn line_numbering_work(content: Vec<u8>, patterns: Vec<Vec<u8>>) -> (usize, usize) {
    let (found, scanned) = byte_hits(&content, &patterns);
    (found.len(), scanned)
}

#[cfg(test)]
mod tests {
    use super::byte_hits;

    fn lines_with_a_match(n: usize) -> Vec<u8> {
        (0..n)
            .flat_map(|i| format!("\0 line {i}\n").into_bytes())
            .collect()
    }

    #[test]
    fn line_numbering_reads_each_byte_once_per_pattern_whatever_the_matches() {
        for n in [1usize, 8_000, 64_000] {
            let content = lines_with_a_match(n);
            let (found, scanned) = byte_hits(&content, &[b"\0".to_vec()]);
            assert_eq!(found.len(), n);
            assert!(
                scanned <= content.len(),
                "{n} matches read {scanned} bytes of a {} byte file",
                content.len()
            );
        }
    }
}
