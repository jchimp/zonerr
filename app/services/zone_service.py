import os
import json
import datetime

import dns.zone
import dns.name
import dns.rdatatype
import dns.node
import dns.rdataclass
import dns.rdata
import dns.exception
import re


def _normalize_dns_name(name: str) -> str:
    """
    Normalize a DNS name component (not email) to a safe form without trailing dot.
    """
    name = (name or "").strip()
    name = name.rstrip(".")
    # collapse repeated dots
    while ".." in name:
        name = name.replace("..", ".")
    return name

def _normalize_rname(email_or_rname: str) -> str:
    """
    Normalize SOA rname. Accepts either:
    - admin.example.com (DNS rname)
    - admin@example.com (email form)
    Returns DNS rname WITHOUT trailing dot.
    """
    s = (email_or_rname or "").strip()
    s = s.rstrip(".")
    if "@" in s:
        s = s.replace("@", ".")
    while ".." in s:
        s = s.replace("..", ".")
    return s

def _assert_no_empty_labels(fqdn: str, field: str):
    # Empty label happens with leading dot, trailing dot in the middle, or double-dot
    if fqdn.startswith(".") or ".." in fqdn:
        raise ValueError(f"Invalid {field}: '{fqdn}' (empty DNS label).")
    # Also catch accidental blank like "" -> ".zone."
    if fqdn.strip(".") == "":
        raise ValueError(f"Invalid {field}: '{fqdn}' (empty DNS name).")


class ZoneService:
    """Manages BIND zone files on disk and a zones.json index."""

    def __init__(self, config):
        self.zone_dir = config["BIND_ZONE_DIR"]
        self.index_path = os.path.join(self.zone_dir, "zones.json")
        os.makedirs(self.zone_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._save_index({})

    # -- index helpers -------------------------------------------------

    def _load_index(self):
        with open(self.index_path, "r") as f:
            return json.load(f)

    def _save_index(self, data):
        with open(self.index_path, "w") as f:
            json.dump(data, f, indent=2)

    def _zone_file(self, zone_name):
        return os.path.join(self.zone_dir, "db." + zone_name)

    # -- serial helpers ------------------------------------------------

    @staticmethod
    def _new_serial():
        today = datetime.date.today().strftime("%Y%m%d")
        return int(today + "01")

    @staticmethod
    def _bump_serial(current):
        today = datetime.date.today().strftime("%Y%m%d")
        today_base = int(today + "00")
        if current >= today_base:
            return current + 1
        return int(today + "01")

    # -- zone CRUD -----------------------------------------------------

    def list_zones(self):
        index = self._load_index()
        result = []
        for name, meta in index.items():
            entry = {
                "name": name,
                "type": meta.get("type", "forward"),
                "file": meta.get("file", ""),
            }
            try:
                records = self.list_records(name)
                entry["record_count"] = len(records)
            except Exception:
                entry["record_count"] = 0
            result.append(entry)
        return sorted(result, key=lambda z: (z["type"], z["name"]))


    def create_zone(self, zone_name, zone_type, soa_ns, soa_email, default_ttl=86400, ns_ip=""):
        index = self._load_index()
        if zone_name in index:
            raise ValueError(f"Zone '{zone_name}' already exists.")

        zone_name = _normalize_dns_name(zone_name)
        if not zone_name:
            raise ValueError("Zone name is required.")

        serial = self._new_serial()
        zone_file = self._zone_file(zone_name)

        # normalize SOA NS input
        soa_ns = _normalize_dns_name(soa_ns) or "ns1"
        # allow user to pass ns1 OR ns1.zone OR ns1.zone.tld — we always derive a usable "ns_short"
        ns_short = soa_ns.split(".")[0] if soa_ns else "ns1"

        # build fully qualified SOA MNAME and validate
        soa_mname = f"{ns_short}.{zone_name}."
        _assert_no_empty_labels(soa_mname, "SOA primary NS (mname)")

        # normalize rname + validate
        rname = _normalize_rname(soa_email) or f"admin.{zone_name}"
        soa_rname = f"{rname}."
        _assert_no_empty_labels(soa_rname, "SOA email (rname)")

        content = f"$TTL {int(default_ttl)}\n"
        content += f"$ORIGIN {zone_name}.\n\n"
        content += f"@   IN  SOA {soa_mname} {soa_rname} (\n"
        content += f"                {serial}   ; Serial\n"
        content += "                3600       ; Refresh\n"
        content += "                900        ; Retry\n"
        content += "                604800     ; Expire\n"
        content += "                86400      ; Minimum TTL\n"
        content += "            )\n\n"
        content += f"@   {int(default_ttl)}   IN  NS  {ns_short}\n"

        # Glue A record (forward zones only typically, but harmless if you allow it)
        if ns_ip:
            content += f"{ns_short}   {int(default_ttl)}   IN  A  {ns_ip}\n"

        # Write file
        with open(zone_file, "w") as f:
            f.write(content)

        # Validate immediately so we don't leave broken zones behind
        try:
            dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)
        except Exception as e:
            # rollback the file on parse error
            try:
                os.remove(zone_file)
            except Exception:
                pass
            raise ValueError(f"Zone file validation failed: {e}")

        # Only save index if it validated
        index[zone_name] = {"type": zone_type, "file": zone_file}
        self._save_index(index)
        

    def get_zone_meta(self, zone_name):
        index = self._load_index()
        if zone_name not in index:
            raise FileNotFoundError(f"Zone '{zone_name}' not found in index.")
        meta = index[zone_name]
        zone_file = meta.get("file", self._zone_file(zone_name))
        if not os.path.exists(zone_file):
            raise FileNotFoundError(f"Zone file for '{zone_name}' not found.")

        soa_info = self._read_soa(zone_name, zone_file)
        return {
            "name": zone_name,
            "type": meta.get("type", "forward"),
            "file": zone_file,
            **soa_info,
        }

    def _read_soa(self, zone_name, zone_file):
        """Parse SOA and default TTL from the raw zone file."""
        info = {"soa_ns": "", "soa_email": "", "serial": 0, "default_ttl": 86400}
        try:
            with open(zone_file, "r") as f:
                content = f.read()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("$TTL"):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        info["default_ttl"] = int(parts[1])
            zone = dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)
            soa_rdataset = zone.find_rdataset("@", dns.rdatatype.SOA)
            for rdata in soa_rdataset:
                info["soa_ns"] = str(rdata.mname).rstrip(".")
                info["soa_email"] = str(rdata.rname).rstrip(".")
                info["serial"] = rdata.serial
                break
        except Exception:
            pass
        return info

    def update_zone_soa(self, zone_name, soa_ns, soa_email, default_ttl):
        zone_file = self._get_zone_file(zone_name)

        with open(zone_file, "r") as f:
            content = f.read()

        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith("$TTL"):
                new_lines.append("$TTL " + str(default_ttl))
            else:
                new_lines.append(line)
        content = "\n".join(new_lines) + "\n"

        zone = dns.zone.from_text(content, origin=zone_name + ".", check_origin=False)
        soa_rdataset = zone.find_rdataset("@", dns.rdatatype.SOA)
        new_soa_rdata = None
        for rdata in soa_rdataset:
            new_serial = self._bump_serial(rdata.serial)
            soa_email_dns = soa_email.replace("@", ".")
            txt = "{ns}. {email}. {serial} {refresh} {retry} {expire} {minimum}".format(
                ns=soa_ns, email=soa_email_dns, serial=new_serial,
                refresh=rdata.refresh, retry=rdata.retry,
                expire=rdata.expire, minimum=rdata.minimum,
            )
            new_soa_rdata = dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.SOA, txt)
            break

        if new_soa_rdata:
            soa_rdataset.clear()
            soa_rdataset.add(new_soa_rdata)

        self._write_zone_file(zone_name, zone, zone_file, default_ttl)

    def delete_zone(self, zone_name):
        index = self._load_index()
        if zone_name in index:
            zone_file = index[zone_name].get("file", self._zone_file(zone_name))
            if os.path.exists(zone_file):
                os.remove(zone_file)
            del index[zone_name]
            self._save_index(index)
        else:
            raise FileNotFoundError(f"Zone '{zone_name}' not found in index.")

    # -- record CRUD ---------------------------------------------------

    def list_records(self, zone_name):
        zone_file = self._get_zone_file(zone_name)
        zone = dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)
        records = []

        for name, rdataset in zone.iterate_rdatasets():
            rdtype_text = dns.rdatatype.to_text(rdataset.rdtype)
            name_str = str(name)
            if name == dns.name.empty:
                name_str = "@"

            for rdata in rdataset:
                value_raw = str(rdata)
                if rdtype_text in ("CNAME", "NS", "PTR", "MX"):
                    value_display = value_raw.rstrip(".")
                else:
                    value_display = value_raw

                record = {
                    "name": name_str,
                    "ttl": rdataset.ttl,
                    "type": rdtype_text,
                    "value": value_display,
                    "value_raw": value_raw,
                }

                if rdtype_text == "SRV":
                    parts = value_raw.split()
                    if len(parts) >= 4:
                        record["priority"] = parts[0]
                        record["weight"] = parts[1]
                        record["port"] = parts[2]
                        record["target"] = parts[3].rstrip(".")

                if rdtype_text == "MX":
                    parts = value_raw.split()
                    if len(parts) >= 2:
                        record["mx_priority"] = parts[0]
                        record["mx_target"] = parts[1].rstrip(".")

                records.append(record)

        return records

    def add_record(self, zone_name, name, ttl, rtype, value):
        zone_file = self._get_zone_file(zone_name)
        meta = self.get_zone_meta(zone_name)
        default_ttl = meta.get("default_ttl", 86400)

        zone = dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)

        rdtype = dns.rdatatype.from_text(rtype)
        if name == "@":
            node_name = dns.name.empty
        else:
            node_name = dns.name.from_text(name, origin=None)

        rdataset = zone.find_rdataset(node_name, rdtype, create=True)
        rdataset.update_ttl(ttl)
        new_rdata = dns.rdata.from_text(dns.rdataclass.IN, rdtype, value)
        rdataset.add(new_rdata)

        self._bump_soa(zone)
        self._write_zone_file(zone_name, zone, zone_file, default_ttl)

    def update_record(self, zone_name, record_index, new_name, new_ttl, rtype, new_value):
        zone_file = self._get_zone_file(zone_name)
        meta = self.get_zone_meta(zone_name)
        default_ttl = meta.get("default_ttl", 86400)

        records = self.list_records(zone_name)
        if record_index < 0 or record_index >= len(records):
            raise IndexError("Record index out of range.")

        zone = dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)

        old = records[record_index]
        old_name_txt = old["name"] if old["name"] != "@" else ""
        if old_name_txt:
            old_node = dns.name.from_text(old_name_txt, origin=None)
        else:
            old_node = dns.name.empty
        old_rdtype = dns.rdatatype.from_text(old["type"])
        old_rdata = dns.rdata.from_text(dns.rdataclass.IN, old_rdtype, old["value_raw"])

        try:
            rdataset = zone.find_rdataset(old_node, old_rdtype)
            rdataset.discard(old_rdata)
            if len(rdataset) == 0:
                zone.delete_rdataset(old_node, old_rdtype)
        except KeyError:
            pass

        new_rdtype = dns.rdatatype.from_text(rtype)
        if new_name == "@":
            new_node = dns.name.empty
        else:
            new_node = dns.name.from_text(new_name, origin=None)
        new_rdataset = zone.find_rdataset(new_node, new_rdtype, create=True)
        new_rdataset.update_ttl(new_ttl)
        new_rdata = dns.rdata.from_text(dns.rdataclass.IN, new_rdtype, new_value)
        new_rdataset.add(new_rdata)

        self._bump_soa(zone)
        self._write_zone_file(zone_name, zone, zone_file, default_ttl)

    def delete_record(self, zone_name, record_index):
        zone_file = self._get_zone_file(zone_name)
        meta = self.get_zone_meta(zone_name)
        default_ttl = meta.get("default_ttl", 86400)

        records = self.list_records(zone_name)
        if record_index < 0 or record_index >= len(records):
            raise IndexError("Record index out of range.")

        old = records[record_index]
        if old["type"] == "SOA":
            raise ValueError("Cannot delete the SOA record.")

        zone = dns.zone.from_file(zone_file, origin=zone_name + ".", check_origin=False)

        old_name_txt = old["name"] if old["name"] != "@" else ""
        if old_name_txt:
            old_node = dns.name.from_text(old_name_txt, origin=None)
        else:
            old_node = dns.name.empty
        old_rdtype = dns.rdatatype.from_text(old["type"])
        old_rdata = dns.rdata.from_text(dns.rdataclass.IN, old_rdtype, old["value_raw"])

        try:
            rdataset = zone.find_rdataset(old_node, old_rdtype)
            rdataset.discard(old_rdata)
            if len(rdataset) == 0:
                zone.delete_rdataset(old_node, old_rdtype)
        except KeyError:
            raise ValueError("Record not found in zone file.")

        self._bump_soa(zone)
        self._write_zone_file(zone_name, zone, zone_file, default_ttl)

    # -- internal helpers ----------------------------------------------

    def _get_zone_file(self, zone_name):
        index = self._load_index()
        if zone_name not in index:
            raise FileNotFoundError(f"Zone '{zone_name}' not found.")
        zone_file = index[zone_name].get("file", self._zone_file(zone_name))
        if not os.path.exists(zone_file):
            raise FileNotFoundError(f"Zone file '{zone_file}' not found on disk.")
        return zone_file

    def _bump_soa(self, zone):
        try:
            soa_rdataset = zone.find_rdataset("@", dns.rdatatype.SOA)
            for rdata in soa_rdataset:
                new_serial = self._bump_serial(rdata.serial)
                txt = "{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}".format(
                    mname=rdata.mname, rname=rdata.rname, serial=new_serial,
                    refresh=rdata.refresh, retry=rdata.retry,
                    expire=rdata.expire, minimum=rdata.minimum,
                )
                new_soa = dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.SOA, txt)
                soa_rdataset.clear()
                soa_rdataset.add(new_soa)
                break
        except KeyError:
            pass

    def _write_zone_file(self, zone_name, zone, zone_file, default_ttl=86400):
        """Write the zone object to file with a readable format."""
        lines = []
        lines.append("$TTL " + str(default_ttl))
        lines.append("$ORIGIN " + zone_name + ".")
        lines.append("")

        # SOA first
        try:
            soa_rdataset = zone.find_rdataset("@", dns.rdatatype.SOA)
            for rdata in soa_rdataset:
                lines.append("@   IN  SOA {mname} {rname} (".format(
                    mname=rdata.mname, rname=rdata.rname))
                lines.append("                {serial}   ; Serial".format(serial=rdata.serial))
                lines.append("                {refresh}       ; Refresh".format(refresh=rdata.refresh))
                lines.append("                {retry}        ; Retry".format(retry=rdata.retry))
                lines.append("                {expire}     ; Expire".format(expire=rdata.expire))
                lines.append("                {minimum}      ; Minimum TTL".format(minimum=rdata.minimum))
                lines.append("            )")
                break
        except KeyError:
            pass

        lines.append("")

        # NS records at apex
        try:
            ns_rdataset = zone.find_rdataset("@", dns.rdatatype.NS)
            for rdata in ns_rdataset:
                lines.append("@   {ttl}   IN  NS  {rdata}".format(
                    ttl=ns_rdataset.ttl, rdata=rdata))
        except KeyError:
            pass

        lines.append("")

        # All other records
        for name, rdataset in zone.iterate_rdatasets():
            rdtype = dns.rdatatype.to_text(rdataset.rdtype)
            if rdtype == "SOA":
                continue

            name_str = str(name)
            if name == dns.name.empty:
                if rdtype == "NS":
                    continue
                name_str = "@"

            for rdata in rdataset:
                lines.append("{name}   {ttl}   IN  {rdtype}  {rdata}".format(
                    name=name_str, ttl=rdataset.ttl, rdtype=rdtype, rdata=rdata))

        lines.append("")
        with open(zone_file, "w") as f:
            f.write("\n".join(lines))
    
    # -- raw zone file reading/writing ----------------------

    def read_raw_zone(self, zone_name):
        """Return the raw zone file contents as a string."""
        zone_file = self._get_zone_file(zone_name)
        with open(zone_file, "r") as f:
            return f.read()

    def write_raw_zone(self, zone_name, content):
        """Write raw content to the zone file. Validates with dnspython first."""
        zone_file = self._get_zone_file(zone_name)

        # Validate the zone content before writing
        try:
            dns.zone.from_text(content, origin=zone_name + ".", check_origin=False)
        except Exception as e:
            raise ValueError(f"Zone file validation failed: {e}")

        with open(zone_file, "w") as f:
            f.write(content)