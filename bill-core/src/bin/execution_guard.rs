use anyhow::{Context, Result, anyhow};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

fn sort_value(value: Value) -> Value {
    match value {
        Value::Object(map) => {
            let ordered: BTreeMap<String, Value> = map
                .into_iter()
                .map(|(key, value)| (key, sort_value(value)))
                .collect();
            let mut out = Map::new();
            for (key, value) in ordered {
                out.insert(key, value);
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(sort_value).collect()),
        other => other,
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

fn read_input(path: Option<&str>) -> Result<String> {
    match path {
        Some("-") | None => {
            let mut buf = String::new();
            std::io::stdin().read_to_string(&mut buf)?;
            Ok(buf)
        }
        Some(path) => fs::read_to_string(path).with_context(|| format!("read intent file {path}")),
    }
}

fn latest_hash(path: &Path) -> Result<String> {
    let raw = match fs::read_to_string(path) {
        Ok(raw) => raw,
        Err(_) => return Ok("GENESIS".to_string()),
    };
    for line in raw.lines().rev() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let value: Value = serde_json::from_str(trimmed).context("parse prior ledger line")?;
        if let Some(hash) = value.get("recordHash").and_then(Value::as_str) {
            return Ok(hash.to_string());
        }
    }
    Ok("GENESIS".to_string())
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let input_path = args.next();
    let ledger = args.next().map(PathBuf::from).unwrap_or_else(|| {
        PathBuf::from("/Users/brain/hedge/.rumbling-hedge/runtime/execution-intents.ledger.jsonl")
    });

    let raw = read_input(input_path.as_deref())?;
    let parsed: Value = serde_json::from_str(&raw).context("intent must be JSON")?;
    let canonical = sort_value(parsed);

    let mode = canonical
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("paper")
        .to_ascii_lowercase();
    let live_flag = canonical
        .get("liveExecution")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let rust_live_allowed =
        env::var("BILL_RUST_EXECUTION_ALLOW_LIVE").unwrap_or_default() == "true";

    if (mode == "live" || live_flag) && !rust_live_allowed {
        return Err(anyhow!(
            "refusing live execution intent: BILL_RUST_EXECUTION_ALLOW_LIVE is not true"
        ));
    }

    let canonical_bytes = serde_json::to_vec(&canonical)?;
    let intent_hash = sha256_hex(&canonical_bytes);
    let previous_hash = latest_hash(&ledger)?;
    let ts = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let record = json!({
        "tsEpoch": ts,
        "intentHash": intent_hash,
        "previousHash": previous_hash,
        "mode": mode,
        "liveExecution": live_flag,
        "intent": canonical,
    });
    let record_canonical = sort_value(record);
    let record_bytes = serde_json::to_vec(&record_canonical)?;
    let record_hash = sha256_hex(&record_bytes);
    let sealed = json!({
        "recordHash": record_hash,
        "record": record_canonical,
    });

    if let Some(parent) = ledger.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new().create(true).append(true).open(&ledger)?;
    writeln!(file, "{}", serde_json::to_string(&sealed)?)?;

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "ok": true,
            "ledger": ledger,
            "intentHash": intent_hash,
            "recordHash": record_hash,
            "previousHash": previous_hash,
            "mode": mode,
            "liveExecution": live_flag
        }))?
    );
    Ok(())
}
