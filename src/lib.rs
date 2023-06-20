use std::collections::HashMap;

use pyo3::{prelude::*, exceptions::PyIndexError, types::{PyString, PyList}};

/// UnionFind.
#[pyclass]
struct UnionFind(Vec<usize>);

#[pymethods]
impl UnionFind {
    #[new]
    #[pyo3(signature = (size=0))]
    fn new(size: usize) -> Self {
        let mut v = Vec::with_capacity(size);
        for i in 0..size {
            v.push(i);
        }
        Self(v)
    }

    fn union(&mut self, a: usize, b: usize) -> PyResult<()> {
        let b_index = self.find(b)?;
        self.0[b_index] = self.find(a)?;
        Ok(())
    }

    fn find(&mut self, mut i: usize) -> PyResult<usize> {
        let mut children = Vec::new();
        while let Some(&parent) = self.0.get(i) {
            if i == parent {
                for child in children {
                    self.0[child] = parent;
                }
                return Ok(i);
            }
            children.push(i);
            i = parent;
        }
        Err(PyIndexError::new_err(""))
    }

    fn find_fast(&self, i: usize) -> PyResult<usize> {
        match self.0.get(i) {
            Some(&parent) => {
                if parent == i {
                    Ok(i)
                } else { 
                    self.find_fast(parent)
                }
            }
            None => Err(PyIndexError::new_err(format!("{i} is not in range")))
        }
    }

    fn add(&mut self, parent: Option<usize>) {
        self.0.push(parent.unwrap_or(self.0.len()))
    }

    fn __str__<'a>(&self, py: Python<'a>) -> &'a PyString {
        PyString::new(py, &format!("{:?}", self.0))
    }

    fn groups<'a>(&self, py: Python<'a>) -> PyResult<&'a PyList> {
        let mut groups: HashMap<_, Vec<usize>> = HashMap::new();
        for i in 0..self.0.len() {
            groups.entry(self.find_fast(i)?).or_default().push(i);
        }
        Ok(PyList::new(py, groups.values().map(|group| PyList::new(py, group))))
    }
}

/// Rust thing
#[pymodule]
fn union_find(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<UnionFind>()?;
    // m.add("__doc__", "editor rust").expect("Test");
    Ok(())
}
