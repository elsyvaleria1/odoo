use pyo3::ffi;
use pyo3::prelude::*;

use crate::ffi_ext::_PyDict_NewPresized;

const MAX_CLONE_DEPTH: usize = 500;

#[pyfunction]
pub fn fast_clone<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py = obj.py();
    unsafe { Ok(Bound::from_owned_ptr(py, clone_inner(py, obj.as_ptr(), 0)?)) }
}

unsafe fn clone_inner(
    py: Python<'_>,
    obj: *mut ffi::PyObject,
    depth: usize,
) -> PyResult<*mut ffi::PyObject> {
    if depth >= MAX_CLONE_DEPTH {
        return Err(pyo3::exceptions::PyRecursionError::new_err(
            "fast_clone: maximum nesting depth exceeded (cyclic or too-deep structure)",
        ));
    }
    unsafe {
        if ffi::PyDict_Check(obj) != 0 {
            let size = ffi::PyDict_Size(obj);
            let new_dict = _PyDict_NewPresized(size);
            if new_dict.is_null() {
                return Err(PyErr::fetch(py));
            }

            let mut pos: ffi::Py_ssize_t = 0;
            let mut key: *mut ffi::PyObject = std::ptr::null_mut();
            let mut val: *mut ffi::PyObject = std::ptr::null_mut();

            while ffi::PyDict_Next(obj, &mut pos, &mut key, &mut val) != 0 {
                if ffi::PyDict_Size(obj) != size {
                    ffi::Py_DECREF(new_dict);
                    return Err(pyo3::exceptions::PyRuntimeError::new_err(
                        "dictionary changed size during iteration",
                    ));
                }
                // PyDict_Next lends key and value: a key's __hash__ run by
                // PyDict_SetItem, or the clone of a nested value, can drop
                // them from the dict being read
                ffi::Py_INCREF(key);
                ffi::Py_INCREF(val);
                let cloned_val = clone_inner(py, val, depth + 1);
                ffi::Py_DECREF(val);
                let cloned_val = match cloned_val {
                    Ok(v) => v,
                    Err(e) => {
                        ffi::Py_DECREF(key);
                        ffi::Py_DECREF(new_dict);
                        return Err(e);
                    }
                };

                let stored = ffi::PyDict_SetItem(new_dict, key, cloned_val);
                ffi::Py_DECREF(key);
                ffi::Py_DECREF(cloned_val);
                if stored < 0 {
                    ffi::Py_DECREF(new_dict);
                    return Err(PyErr::fetch(py));
                }
            }

            return Ok(new_dict);
        }

        if ffi::PyList_Check(obj) != 0 {
            // the length is read again at every step, as a list iterator does:
            // cloning an item can run code that resizes the list being read
            let mut items = Vec::with_capacity(ffi::PyList_GET_SIZE(obj).max(0) as usize);
            let mut i: ffi::Py_ssize_t = 0;
            while i < ffi::PyList_GET_SIZE(obj) {
                let item = ffi::PyList_GET_ITEM(obj, i);
                ffi::Py_INCREF(item);
                let cloned = clone_inner(py, item, depth + 1);
                ffi::Py_DECREF(item);
                match cloned {
                    Ok(v) => items.push(v),
                    Err(e) => {
                        release(items);
                        return Err(e);
                    }
                }
                i += 1;
            }
            return finish(py, items, ffi::PyList_New, |list, i, v| {
                ffi::PyList_SET_ITEM(list, i, v)
            });
        }

        if ffi::PyTuple_Check(obj) != 0 {
            let n = ffi::PyTuple_GET_SIZE(obj);
            let mut items = Vec::with_capacity(n.max(0) as usize);
            for i in 0..n {
                match clone_inner(py, ffi::PyTuple_GET_ITEM(obj, i), depth + 1) {
                    Ok(v) => items.push(v),
                    Err(e) => {
                        release(items);
                        return Err(e);
                    }
                }
            }
            return finish(py, items, ffi::PyTuple_New, |tuple, i, v| {
                ffi::PyTuple_SET_ITEM(tuple, i, v)
            });
        }

        ffi::Py_INCREF(obj);
        Ok(obj)
    }
}

// The container is created only once every item is cloned: one allocated
// with empty slots and filled while cloning is tracked by the collector, so
// code a clone runs (a key's __hash__) could reach it and read an empty slot.
unsafe fn finish(
    py: Python<'_>,
    items: Vec<*mut ffi::PyObject>,
    new: unsafe extern "C" fn(ffi::Py_ssize_t) -> *mut ffi::PyObject,
    set: impl Fn(*mut ffi::PyObject, ffi::Py_ssize_t, *mut ffi::PyObject),
) -> PyResult<*mut ffi::PyObject> {
    unsafe {
        let container = new(items.len() as ffi::Py_ssize_t);
        if container.is_null() {
            release(items);
            return Err(PyErr::fetch(py));
        }
        for (i, item) in items.into_iter().enumerate() {
            set(container, i as ffi::Py_ssize_t, item);
        }
        Ok(container)
    }
}

unsafe fn release(items: Vec<*mut ffi::PyObject>) {
    for item in items {
        unsafe { ffi::Py_DECREF(item) };
    }
}
