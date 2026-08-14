//! Prints the vocabulary's JSON Schema.
//!
//!     ptn-schema            # the whole document
//!     ptn-schema > kernel.schema.json
//!
//! This is the handoff artifact: every other implementation of the vocabulary
//! is generated from, or checked against, this output.

fn main() {
    let schemas = ptn_vocab::schemas();
    match serde_json::to_string_pretty(&schemas) {
        Ok(s) => println!("{s}"),
        Err(e) => {
            eprintln!("ptn-schema: {e}");
            std::process::exit(1);
        }
    }
}
