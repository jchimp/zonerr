import os
import re
import datetime
from collections import Counter


class StatsService:
    """Parses BIND query.log and produces query statistics."""

    # Matches BIND query log lines — handles optional hex pointer after "client"
    QUERY_RE = re.compile(
        r"^(?P<date>\d{2}-\w{3}-\d{4})\s+"
        r"(?P<time>[\d:.]+)\s+"
        r"client\s+(?:@0x[0-9a-f]+\s+)?"
        r"(?P<src_ip>[\d.]+)#(?P<src_port>\d+)\s+"
        r"\([^)]*\):\s+query:\s+"
        r"(?P<name>\S+)\s+"
        r"IN\s+(?P<qtype>\w+)"
    )

    def __init__(self, config):
        self.log_dir = config.get("BIND_LOG_DIR", "/var/log/bind")

    def _read_log_lines(self, max_lines=10000):
        """Read the last N lines of query.log."""
        log_path = os.path.join(self.log_dir, "query.log")
        if not os.path.isfile(log_path):
            return []
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
            if max_lines and max_lines > 0:
                lines = lines[-max_lines:]
            return lines
        except Exception:
            return []

    def parse_query_log(self, max_lines=10000):
        """Parse query.log and return list of query dicts."""
        lines = self._read_log_lines(max_lines)
        queries = []
        for line in lines:
            m = self.QUERY_RE.match(line.strip())
            if m:
                queries.append({
                    "date": m.group("date"),
                    "time": m.group("time"),
                    "source_ip": m.group("src_ip"),
                    "name": m.group("name").rstrip("."),
                    "type": m.group("qtype"),
                })
        return queries

    def get_overview_stats(self, max_lines=10000):
        """Return overview statistics for the dashboard."""
        queries = self.parse_query_log(max_lines)

        if not queries:
            return {
                "total_queries": 0,
                "today_queries": 0,
                "unique_names": 0,
                "unique_clients": 0,
                "top_names": [],
                "top_clients": [],
                "by_type": {},
            }

        today_str = datetime.date.today().strftime("%d-%b-%Y")

        name_counter = Counter()
        client_counter = Counter()
        type_counter = Counter()
        today_count = 0

        for q in queries:
            name_counter[q["name"]] += 1
            client_counter[q["source_ip"]] += 1
            type_counter[q["type"]] += 1
            if q["date"] == today_str:
                today_count += 1

        return {
            "total_queries": len(queries),
            "today_queries": today_count,
            "unique_names": len(name_counter),
            "unique_clients": len(client_counter),
            "top_names": name_counter.most_common(10),
            "top_clients": client_counter.most_common(10),
            "by_type": dict(type_counter.most_common()),
        }

    def get_zone_stats(self, zone_name, max_lines=10000):
        """Return query statistics filtered to a specific zone."""
        queries = self.parse_query_log(max_lines)

        zone_suffix = zone_name.rstrip(".")
        zone_queries = [q for q in queries if q["name"].endswith(zone_suffix)]

        if not zone_queries:
            return {
                "total_queries": 0,
                "top_names": [],
                "by_type": {},
            }

        name_counter = Counter()
        type_counter = Counter()

        for q in zone_queries:
            name_counter[q["name"]] += 1
            type_counter[q["type"]] += 1

        return {
            "total_queries": len(zone_queries),
            "top_names": name_counter.most_common(10),
            "by_type": dict(type_counter.most_common()),
        }
