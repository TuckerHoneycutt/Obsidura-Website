mod config;
mod identity;
mod routes;

use tokio::net::TcpListener;

#[tokio::main]
async fn main() {
    let app = routes::hub::router().merge(routes::setup::router());

    let listener = TcpListener::bind("0.0.0.0:9080").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
