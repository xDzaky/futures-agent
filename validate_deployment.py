#!/usr/bin/env python3
"""
Deployment Validation Script
Run before deploying to ensure everything is ready.
"""

import os
import sys
import subprocess

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    BLUE = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{text}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_check(name, passed):
    icon = "✅" if passed else "❌"
    color = Colors.GREEN if passed else Colors.RED
    print(f"{icon} {color}{name}{Colors.RESET}")

def main():
    print(f"\n{Colors.GREEN}{Colors.BOLD}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║   RAILWAY DEPLOYMENT VALIDATION                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")
    
    results = []
    
    # 1. Python syntax check
    print_header("1. Python Syntax Check")
    core_files = [
        "realtime_monitor.py",
        "ai_research_agent.py",
        "trending_tracker.py",
        "news_feeds.py",
        "news_correlator.py",
        "trade_db.py",
        "signal_scraper.py",
    ]
    
    for file in core_files:
        if os.path.exists(file):
            result = subprocess.run(["python3", "-m", "py_compile", file], capture_output=True)
            passed = result.returncode == 0
            print_check(file, passed)
            results.append(passed)
        else:
            print_check(f"{file} (missing)", False)
            results.append(False)
    
    # 2. Config files
    print_header("2. Configuration Files")
    config_files = ["requirements.txt", "nixpacks.toml", "start_railway.sh", ".railwayignore"]
    for file in config_files:
        exists = os.path.exists(file)
        print_check(file, exists)
        results.append(exists)
    
    # 3. Check startup script executable
    print_header("3. Startup Script")
    if os.path.exists("start_railway.sh"):
        is_exec = os.access("start_railway.sh", os.X_OK)
        print_check("start_railway.sh executable", is_exec)
        results.append(is_exec)
    
    # 4. Documentation
    print_header("4. Documentation")
    docs = ["DEPLOY.md", ".env.example"]
    for doc in docs:
        exists = os.path.exists(doc)
        print_check(doc, exists)
        results.append(exists)
    
    # Summary
    print_header("SUMMARY")
    passed = sum(results)
    total = len(results)
    
    print(f"{Colors.BOLD}Result: {passed}/{total} checks passed{Colors.RESET}\n")
    
    if passed == total:
        print(f"{Colors.GREEN}✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT!{Colors.RESET}\n")
        print("Next steps:")
        print("1. Set environment variables in Railway Dashboard")
        print("2. Deploy from GitHub or use 'railway up'")
        print("3. Monitor logs for any errors")
        return 0
    else:
        print(f"{Colors.RED}❌ SOME CHECKS FAILED{Colors.RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
