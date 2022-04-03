#!/bin/sh

ulimit -n 60000
ulimit -u 60000
sysctl net.ipv4.ip_local_port_range="15000 61000"
sysctl net.ipv4.tcp_fin_timeout=20


