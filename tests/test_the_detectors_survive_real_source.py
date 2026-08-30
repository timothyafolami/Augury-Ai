"""The detectors, run through the parser over files that look like code.

Every signal test so far hands `signals_in_source` a line. That checks the
regex and nothing else: not that tree-sitter parses the file, not that the
Cartographer reaches the detector, not that a construct still matches once it
is surrounded by the imports, comments, generics and nesting that real source
has around it.

Those are different questions, and the gap between them is where a detector
that passes its unit test finds nothing in practice. A pattern anchored on
`\\bunsafe\\s*[{]` matches the probe `unsafe { *p = 5; }` and would also have
to survive `pub unsafe fn write_at(&mut self, ...) -> Result<(), Error> {`.

So this maps whole files, through `Cartographer`, and asserts on what the
pipeline actually produced. Rust, C++ and Java, because those are the three
languages with no case in the evaluation suite and therefore no end-to-end
measurement of any kind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from augury.core.cartography.mapper import Cartographer
from augury.core.cartography.model import Signal

RUST = """\
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::thread;

/// A cache shared across worker threads.
///
/// The `unsafe` block below is deliberate: it writes through a raw pointer
/// obtained from the map, which the borrow checker cannot verify.
pub struct Cache {
    entries: Arc<Mutex<HashMap<String, Vec<u8>>>>,
}

impl Cache {
    pub fn new() -> Self {
        Self { entries: Arc::new(Mutex::new(HashMap::new())) }
    }

    pub fn warm(&self, keys: Vec<String>) {
        for key in keys {
            let entries = Arc::clone(&self.entries);
            thread::spawn(move || {
                let mut guard = entries.lock().unwrap();
                guard.insert(key, Vec::new());
            });
        }
    }

    pub unsafe fn write_at(&self, target: *mut u8, byte: u8) {
        *target = byte;
    }
}
"""

CPP = """\
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

namespace inventory {

// Formats one audit line into a fixed buffer.
class Auditor {
 public:
  explicit Auditor(const std::string& path) : path_(path) {}

  void Record(const char* actor, const char* action) {
    char line[128];
    std::lock_guard<std::mutex> held(guard_);
    sprintf(line, "%s did %s", actor, action);
    strcat(buffer_, line);
  }

  void Start() {
    std::thread worker([this] { Flush(); });
    worker.detach();
  }

 private:
  void Flush();

  std::string path_;
  std::mutex guard_;
  char buffer_[4096];
};

}  // namespace inventory
"""

JAVA = """\
package com.example.inventory;

import java.io.InputStream;
import java.io.ObjectInputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Restores a snapshot and reindexes it. */
public final class Restore {

    private final ExecutorService pool = Executors.newFixedThreadPool(4);

    public Object load(InputStream in) throws Exception {
        // Trusts whatever the stream contains.
        try (ObjectInputStream stream = new ObjectInputStream(in)) {
            return stream.readObject();
        }
    }

    public void reindex(String target) throws Exception {
        Runtime.getRuntime().exec("reindex --target " + target);
    }

    public synchronized void await() {
        pool.shutdown();
    }
}
"""


def _signals(root: Path, name: str, source: str) -> frozenset[Signal]:
    (root / name).write_text(source, encoding="utf-8")
    found = {module.path: module.signals for module in Cartographer(root).map().modules}
    assert name in found, f"{name} was not mapped at all: {sorted(found)}"
    return found[name]


@pytest.mark.parametrize(
    "name,source,expected",
    [
        ("cache.rs", RUST, {Signal.CONCURRENCY, Signal.SECURITY}),
        ("auditor.cpp", CPP, {Signal.CONCURRENCY, Signal.SECURITY}),
        ("Restore.java", JAVA, {Signal.CONCURRENCY, Signal.SECURITY}),
    ],
    ids=["rust", "cpp", "java"],
)
def test_a_realistic_file_raises_what_it_contains(
    tmp_path: Path, name: str, source: str, expected: set[Signal]
) -> None:
    raised = _signals(tmp_path, name, source)

    assert expected <= set(raised), (
        f"{name} raised {sorted(s.value for s in raised)}, missing "
        f"{sorted(s.value for s in expected - set(raised))}"
    )


def test_an_unsafe_fn_signature_still_matches(tmp_path: Path) -> None:
    """The probe was `unsafe { ... }`. Real Rust writes `pub unsafe fn` with a
    receiver, arguments and a return type before any brace appears."""
    assert Signal.SECURITY in _signals(tmp_path, "cache.rs", RUST)


def test_a_lock_guard_declaration_counts_as_concurrency(tmp_path: Path) -> None:
    """`std::lock_guard<std::mutex> held(guard_);` carries the template
    arguments the one-line probe did not."""
    assert Signal.CONCURRENCY in _signals(tmp_path, "auditor.cpp", CPP)


def test_a_file_with_none_of_it_stays_quiet(tmp_path: Path) -> None:
    """The guard that makes the three above mean something."""
    plain = """\
package com.example.inventory;

/** A value object. */
public final class Sku {
    private final String code;

    public Sku(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
"""
    raised = _signals(tmp_path, "Sku.java", plain)

    assert Signal.CONCURRENCY not in raised
    assert Signal.SECURITY not in raised
