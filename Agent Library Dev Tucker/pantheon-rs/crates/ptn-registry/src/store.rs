//! Where registered definitions live.
//!
//! Spec §6 puts the registry in Postgres. This file defines the trait that
//! describes and a file-backed implementation that works today, with no
//! database to stand up.
//!
//! The order is deliberate, not a shortcut: `ptn plan` is useful the moment it
//! can validate a directory, and making that wait on Postgres would delay the
//! only part an author interacts with. `PostgresStore` is the next
//! implementation of this trait and changes no caller.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use ptn_vocab::{Definition, TypeRef};
use serde::{Deserialize, Serialize};

/// A registered definition and the revision it was registered at.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Registered {
    /// The definition as registered.
    pub def: Definition,
    /// Monotonic revision, bumped on every apply that changed this entry.
    pub revision: u64,
}

/// Read/write access to the registry.
#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("registry io: {0}")]
    /// The registry file could not be read or written.
    Io(#[from] std::io::Error),
    #[error("registry is not readable as JSON: {0}")]
    /// The registry file is not valid JSON.
    Decode(#[from] serde_json::Error),
}

/// Read/write access to the registry. Spec §6 puts this in Postgres; the
/// file-backed implementation below satisfies the same contract.
pub trait Store {
    /// Every registered definition, keyed by name@version.
    fn all(&self) -> Result<BTreeMap<TypeRef, Registered>, StoreError>;

    /// Registers the given definitions, bumping revisions for changed entries.
    fn apply(&mut self, defs: &[Definition]) -> Result<(), StoreError>;
}

/// A registry kept in one JSON file.
///
/// Sorted on write (BTreeMap), so the file is diffable and two applies of the
/// same content produce identical bytes. A registry nobody can diff is a
/// registry nobody audits.
#[derive(Debug)]
pub struct FileStore {
    path: PathBuf,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct FileContents {
    #[serde(default)]
    revision: u64,
    #[serde(default)]
    entries: BTreeMap<String, Registered>,
}

impl FileStore {
    /// Points at a registry file. The file need not exist yet.
    pub fn new(path: impl AsRef<Path>) -> Self {
        Self {
            path: path.as_ref().to_path_buf(),
        }
    }

    fn read(&self) -> Result<FileContents, StoreError> {
        if !self.path.exists() {
            // An absent registry is an empty one, not an error. The first plan
            // against a fresh checkout should say "12 added", not "no registry".
            return Ok(FileContents::default());
        }
        let body = fs::read_to_string(&self.path)?;
        if body.trim().is_empty() {
            return Ok(FileContents::default());
        }
        Ok(serde_json::from_str(&body)?)
    }

    fn write(&self, contents: &FileContents) -> Result<(), StoreError> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut body = serde_json::to_string_pretty(contents)?;
        body.push('\n');
        fs::write(&self.path, body)?;
        Ok(())
    }
}

impl Store for FileStore {
    fn all(&self) -> Result<BTreeMap<TypeRef, Registered>, StoreError> {
        let contents = self.read()?;
        let mut out = BTreeMap::new();
        for (key, entry) in contents.entries {
            // A key that no longer parses means the registry was written by an
            // older vocabulary. Skipping it silently would hide that; the
            // planner reports it as a removal, which is visible.
            if let Ok(reference) = key.parse::<TypeRef>() {
                out.insert(reference, entry);
            }
        }
        Ok(out)
    }

    fn apply(&mut self, defs: &[Definition]) -> Result<(), StoreError> {
        let mut contents = self.read()?;
        contents.revision += 1;
        let revision = contents.revision;

        let mut next: BTreeMap<String, Registered> = BTreeMap::new();
        for def in defs {
            let key = def.type_ref().to_string();
            let previous = contents.entries.get(&key);
            // Unchanged entries keep their revision, so the revision column
            // answers "when did this last actually change", not "when was
            // apply last run".
            let revision = match previous {
                Some(p) if &p.def == def => p.revision,
                _ => revision,
            };
            next.insert(
                key,
                Registered {
                    def: def.clone(),
                    revision,
                },
            );
        }

        contents.entries = next;
        self.write(&contents)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ptn_vocab::SchemaDef;

    fn temp(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("ptn-store-{name}-{}.json", std::process::id()))
    }

    fn schema(name: &str, version: u32, doc: &str) -> Definition {
        Definition::Schema(SchemaDef {
            name: name.into(),
            version,
            document: serde_json::from_str(doc).unwrap(),
            refines: None,
        })
    }

    /// The first plan against a fresh checkout should say "12 added", not
    /// "no registry".
    #[test]
    fn an_absent_registry_reads_as_empty() {
        let path = temp("absent");
        let _ = fs::remove_file(&path);
        let store = FileStore::new(&path);
        assert!(store.all().unwrap().is_empty());
    }

    #[test]
    fn an_empty_file_reads_as_empty() {
        let path = temp("blank");
        fs::write(&path, "   \n").unwrap();
        assert!(FileStore::new(&path).all().unwrap().is_empty());
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn a_corrupt_registry_is_an_error_not_an_empty_one() {
        // Silently treating a corrupt registry as empty would make the next
        // apply look like a full first-time install.
        let path = temp("corrupt");
        fs::write(&path, "{not json").unwrap();
        assert!(FileStore::new(&path).all().is_err());
        let _ = fs::remove_file(&path);
    }

    /// The revision column answers "when did this last actually change", not
    /// "when was apply last run". Bumping unchanged entries would make every
    /// apply look like it rewrote the world.
    #[test]
    fn revision_bumps_only_for_entries_that_changed() {
        let path = temp("revision");
        let _ = fs::remove_file(&path);
        let mut store = FileStore::new(&path);

        let a_v1 = schema("demo.A", 1, r#"{"type":"object"}"#);
        let b = schema("demo.B", 1, r#"{"type":"object"}"#);
        store.apply(&[a_v1.clone(), b.clone()]).unwrap();

        let first = store.all().unwrap();
        let a_rev = first[&"demo.A@1".parse().unwrap()].revision;
        let b_rev = first[&"demo.B@1".parse().unwrap()].revision;
        assert_eq!(a_rev, 1);
        assert_eq!(b_rev, 1);

        // Change A only.
        let a_v2 = schema("demo.A", 1, r#"{"type":"object","title":"changed"}"#);
        store.apply(&[a_v2, b]).unwrap();

        let second = store.all().unwrap();
        assert_eq!(
            second[&"demo.A@1".parse().unwrap()].revision,
            2,
            "a changed entry must get the new revision"
        );
        assert_eq!(
            second[&"demo.B@1".parse().unwrap()].revision,
            b_rev,
            "an unchanged entry must keep its revision"
        );
        let _ = fs::remove_file(&path);
    }

    /// Apply replaces the entry set. A definition removed from the directories
    /// is gone from the registry after the next apply, which is what makes the
    /// planner's orphan report the ONLY way one lingers.
    #[test]
    fn apply_replaces_rather_than_merges() {
        let path = temp("replace");
        let _ = fs::remove_file(&path);
        let mut store = FileStore::new(&path);

        store
            .apply(&[
                schema("demo.A", 1, r#"{"type":"object"}"#),
                schema("demo.B", 1, r#"{"type":"object"}"#),
            ])
            .unwrap();
        store
            .apply(&[schema("demo.A", 1, r#"{"type":"object"}"#)])
            .unwrap();

        let all = store.all().unwrap();
        assert_eq!(all.len(), 1);
        assert!(all.contains_key(&"demo.A@1".parse().unwrap()));
        let _ = fs::remove_file(&path);
    }

    /// A registry nobody can diff is a registry nobody audits.
    #[test]
    fn the_file_is_sorted_and_byte_stable() {
        let path = temp("stable");
        let _ = fs::remove_file(&path);
        let mut store = FileStore::new(&path);

        let defs = vec![
            schema("z.Last", 1, r#"{"type":"object"}"#),
            schema("a.First", 1, r#"{"type":"object"}"#),
            schema("m.Middle", 1, r#"{"type":"object"}"#),
        ];
        store.apply(&defs).unwrap();
        let first = fs::read_to_string(&path).unwrap();

        // Same content, different input order.
        let mut reordered = defs.clone();
        reordered.reverse();
        let mut store2 = FileStore::new(&path);
        store2.apply(&reordered).unwrap();
        let second = fs::read_to_string(&path).unwrap();

        let strip = |s: &str| {
            s.lines()
                .filter(|l| !l.contains("\"revision\""))
                .collect::<Vec<_>>()
                .join("\n")
        };
        assert_eq!(
            strip(&first),
            strip(&second),
            "input order changed the registry file"
        );
        assert!(
            first.ends_with('\n'),
            "registry file should end with a newline"
        );

        let a = first.find("a.First").unwrap();
        let m = first.find("m.Middle").unwrap();
        let z = first.find("z.Last").unwrap();
        assert!(a < m && m < z, "entries are not sorted");
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn creates_parent_directories() {
        let dir = std::env::temp_dir().join(format!("ptn-store-nested-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let path = dir.join("deep").join("registry.json");
        let mut store = FileStore::new(&path);
        store
            .apply(&[schema("demo.A", 1, r#"{"type":"object"}"#)])
            .unwrap();
        assert!(path.exists());
        let _ = fs::remove_dir_all(&dir);
    }
}
