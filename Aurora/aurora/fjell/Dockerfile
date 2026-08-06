FROM rust:1.85@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4 as builder

WORKDIR /app

# Simple full build - Use if cache trick breaks again
COPY . .
RUN cargo build --release

# Cached build: pre-compile deps with a placeholder, then build the real bin only when src changes.
# COPY Cargo.toml Cargo.lock ./
# RUN mkdir -p src && echo "fn main() {}" > src/main.rs
# RUN cargo build --release --bin fjell
# RUN rm -rf src
# COPY src ./src
# RUN touch src/main.rs
# RUN cargo build --release --bin fjell

FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818
# Get up to date index of packages -> install ca-certificates so fjell can be trusted in browser (no bloated install recommends) -> remove package index list (we only get packages
# on startup, not during runtime, so this wastes 50Mb of what should be a super-lite application image)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/fjell /app/fjell
EXPOSE 8080
CMD ["/app/fjell"]
