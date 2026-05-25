# Replication

## Replication — How It Works
Here's the practical overview for setting up master/slave with Zonerr:

### Architecture

```
┌──────────────────┐         zone transfer         ┌──────────────────┐
│  MASTER (Site A) │  ──────── TCP/53 ──────────▶ │  SLAVE (Site B)  │
│  Zonerr + BIND   │         NOTIFY + AXFR         │  BIND only       │
│  10.0.0.1        │                               │  10.0.0.2        │
└──────────────────┘                               └──────────────────┘
```

The master holds the zone files and pushes changes. The slave pulls copies and serves them read-only.

---

### Step 1: Configure the Master (Zonerr)

In Zonerr → **Settings → Replication**:
- **Role:** Master
- **Allow Transfer:** `10.0.0.2` (slave IP)
- **Also Notify:** `10.0.0.2`
- Click **Save & Apply**. 

This rewrites every zone block in `named.conf.local` to include:
```
zone "example.com" {  
	type master;  
	file "/etc/bind/zones/db.example.com";  
	allow-transfer { 10.0.0.2; };  
	also-notify { 10.0.0.2; };  
	notify yes;  
};  
```

---

### Step 2: Set Up the Slave Server
The slave is a **standalone BIND server** — it doesn't need Zonerr (though it could run a read-only instance). Minimal setup:

**Install BIND:**
```Shell
apt install bind9 bind9-utils  
```

**Edit `/etc/bind/named.conf.local`:**
```
zone "example.com" {  
	type slave;  
	file "/var/cache/bind/db.example.com";  
	masters { 10.0.0.1; };  
};  
```
> One block per zone you want replicated.

**Edit `/etc/bind/named.conf.options`:**
```
options {  
	directory "/var/cache/bind";  
	allow-transfer { none; };  

	recursion yes;  

	listen-on { any; };  

	forwarders {  
		8.8.8.8;  
		1.1.1.1;  
	};  
};  
```

**Restart:**
```shell
systemctl restart bind9  
```

---

### Step 3: Verify

**On the master:**
```shell
# Check that the slave pulled the zone  
docker exec zonerr-bind cat /var/log/bind/default.log | grep "transfer of"  
```

You should see lines like:
```
transfer of 'example.com/IN': AXFR started
transfer of 'example.com/IN': AXFR ended
```

**On the slave:**
```shell
# Check the zone was received  
dig @localhost example.com SOA  

# Check the zone file was created  
ls -la /var/cache/bind/db.example.com  
```

---

### Step 4: Test Ongoing Replication

1. Add a record in Zonerr on the master
2. Zonerr calls `rndc reload` → BIND bumps the serial → sends NOTIFY to slave
3. Slave sees the new serial → pulls an AXFR/IXFR
4. Query the slave — new record should appear within seconds
	```
	# On slave  
	dig @localhost www.example.com A  
	```

---

### Gotchas

| Issue                            | Solution                                                       |
| -------------------------------- | -------------------------------------------------------------- |
| Slave never pulls                | Check firewall — TCP 53 must be open between master and slave  |
| "refused" on transfer            | Verify `allow-transfer` on master includes slave IP            |
| Stale data on slave              | Check serial numbers — master serial must be higher than slave |
| Slave zones disappear on restart | Make sure `file` path is writable by the `bind` user           |

