#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {

struct GateInput {
  std::string mode = "paper";
  double net_edge_pct = 0.0;
  double stake = 0.0;
  bool kill_switch = false;
  bool live_readiness = false;
};

struct GateResult {
  bool ok = false;
  std::string stage = "blocked";
  std::vector<std::string> blockers;
};

std::optional<double> parse_double(std::string_view value) {
  char* end = nullptr;
  const std::string owned(value);
  const double parsed = std::strtod(owned.c_str(), &end);
  if (end == owned.c_str() || *end != '\0') {
    return std::nullopt;
  }
  return parsed;
}

bool parse_bool(std::string_view value) {
  return value == "true" || value == "1" || value == "yes";
}

std::string json_escape(std::string_view value) {
  std::string out;
  for (const char ch : value) {
    switch (ch) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default: out += ch; break;
    }
  }
  return out;
}

GateResult evaluate_gate(const GateInput& input) {
  GateResult result;
  if (input.kill_switch) {
    result.blockers.emplace_back("kill-switch-active");
  }
  if (input.net_edge_pct <= 0.0) {
    result.blockers.emplace_back("non-positive-net-edge");
  }
  if (input.stake <= 0.0) {
    result.blockers.emplace_back("zero-stake");
  }
  if (input.mode == "live" && !input.live_readiness) {
    result.blockers.emplace_back("live-readiness-not-approved");
  }
  if (input.mode != "paper" && input.mode != "live") {
    result.blockers.emplace_back("unsupported-mode");
  }
  result.ok = result.blockers.empty();
  result.stage = result.ok ? input.mode : "blocked";
  return result;
}

void print_gate_json(const GateInput& input, const GateResult& result) {
  std::cout
    << "{\n"
    << "  \"command\": \"bill-core gate\",\n"
    << "  \"engine\": \"bill-core-cpp20\",\n"
    << "  \"ok\": " << (result.ok ? "true" : "false") << ",\n"
    << "  \"stage\": \"" << json_escape(result.stage) << "\",\n"
    << "  \"input\": {\n"
    << "    \"mode\": \"" << json_escape(input.mode) << "\",\n"
    << "    \"netEdgePct\": " << input.net_edge_pct << ",\n"
    << "    \"stake\": " << input.stake << ",\n"
    << "    \"killSwitch\": " << (input.kill_switch ? "true" : "false") << ",\n"
    << "    \"liveReadiness\": " << (input.live_readiness ? "true" : "false") << "\n"
    << "  },\n"
    << "  \"blockers\": [";
  for (std::size_t index = 0; index < result.blockers.size(); ++index) {
    if (index > 0) std::cout << ", ";
    std::cout << "\"" << json_escape(result.blockers[index]) << "\"";
  }
  std::cout << "]\n}\n";
}

void print_usage() {
  std::cout
    << "bill-core gate --mode paper|live --net-edge-pct N --stake N "
    << "--kill-switch true|false --live-readiness true|false\n";
}

int run_gate(int argc, char** argv) {
  GateInput input;
  for (int i = 2; i < argc; ++i) {
    const std::string key(argv[i]);
    const auto require_value = [&](const char* name) -> std::string {
      if (i + 1 >= argc) {
        std::cerr << "missing value for " << name << "\n";
        std::exit(2);
      }
      return std::string(argv[++i]);
    };

    if (key == "--mode") {
      input.mode = require_value("--mode");
    } else if (key == "--net-edge-pct") {
      const auto parsed = parse_double(require_value("--net-edge-pct"));
      if (!parsed) {
        std::cerr << "invalid --net-edge-pct\n";
        return 2;
      }
      input.net_edge_pct = *parsed;
    } else if (key == "--stake") {
      const auto parsed = parse_double(require_value("--stake"));
      if (!parsed) {
        std::cerr << "invalid --stake\n";
        return 2;
      }
      input.stake = *parsed;
    } else if (key == "--kill-switch") {
      input.kill_switch = parse_bool(require_value("--kill-switch"));
    } else if (key == "--live-readiness") {
      input.live_readiness = parse_bool(require_value("--live-readiness"));
    } else {
      std::cerr << "unknown option: " << key << "\n";
      return 2;
    }
  }

  const auto result = evaluate_gate(input);
  print_gate_json(input, result);
  return result.ok ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2 || std::string_view(argv[1]) == "--help") {
    print_usage();
    return argc < 2 ? 2 : 0;
  }
  if (std::string_view(argv[1]) == "gate") {
    return run_gate(argc, argv);
  }
  std::cerr << "unknown command: " << argv[1] << "\n";
  print_usage();
  return 2;
}
