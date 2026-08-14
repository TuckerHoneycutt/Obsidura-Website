#![warn(missing_docs)]

//! The definition registry and the plan/apply cycle — chunk 2 of the P0 build
//! plan.
//!
//! Spec §7: `ptn plan` shows a diff against the registry; `ptn apply`
//! registers; invalid definitions are rejected at plan time with errors naming
//! the file, field, and rule violated. All three of those are what `diag.rs`
//! exists for.
//!
//! What "validated" means here is deliberately narrow and deliberately total:
//! every ref resolves, every used verb is one its resource exposes, and every
//! wired pair agrees about the value crossing their seam. Nothing about a
//! definition's *meaning* is checked, because meaning lives in Records and the
//! executor's whole relationship with one is `validate(schema, data)`.

pub mod diag;
pub mod load;
pub mod plan;
pub mod store;
pub mod validate;

pub use diag::{Diagnostic, Diagnostics, Rule};
pub use load::{load, Loaded, Located};
pub use plan::{plan, Change, Plan, PlannedChange};
pub use store::{FileStore, Registered, Store, StoreError};
