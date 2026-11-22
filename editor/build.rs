fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        println!("cargo:rerun-if-changed=assets/pysocha.rc");
        println!("cargo:rerun-if-changed=assets/pysocha.ico");
        embed_resource::compile("assets/pysocha.rc", embed_resource::NONE)
            .manifest_required()
            .expect("embed the Pysocha application icon");
    }
}
