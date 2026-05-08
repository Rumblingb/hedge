use bill_core;

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: pipeline <csv_path> [max_bars]");
        std::process::exit(1);
    }
    let path = &args[1];
    let max_bars: Option<usize> = args.get(2).and_then(|s| s.parse().ok());
    let result = bill_core::run_pipeline(path, max_bars)?;
    let json = serde_json::to_string_pretty(&result)?;
    println!("{}", json);
    Ok(())
}
