#!/usr/bin/env python3
"""
Railway Deployment Verification Script
========================================
Checks if all required files and configurations are ready for Railway deployment.

Usage:
    python verify_railway_deploy.py
"""

import os
import sys
from pathlib import Path

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def check_file(filepath: str, required: bool = True) -> bool:
    """Check if file exists."""
    exists = Path(filepath).exists()
    status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
    req = "(REQUIRED)" if required else "(OPTIONAL)"
    print(f"  {status} {filepath} {req}")
    
    if required and not exists:
        return False
    return True

def check_env_var(var: str, env: dict) -> bool:
    """Check if env var key exists in template (value can be empty)."""
    exists = var in env
    status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
    print(f"  {status} {var}")
    
    if not exists:
        return False
    return True

def main():
    print("\n" + "="*60)
    print("🚂 Railway Deployment Verification")
    print("="*60 + "\n")
    
    base_dir = Path(__file__).parent
    os.chdir(base_dir)
    
    all_good = True
    
    # Check required files
    print("📁 Required Files:")
    required_files = [
        "agent.py",
        "realtime_monitor.py",
        "requirements.txt",
        "Procfile",
        "railway.json",
        "nixpacks.toml",
        "package.json",
        "runtime.txt",
    ]
    for f in required_files:
        if not check_file(f, required=True):
            all_good = False
    
    print()
    
    # Check optional but recommended files
    print("📁 Optional Files:")
    optional_files = [
        ".env.example",
        "README.md",
        "RAILWAY_DEPLOYMENT.md",
    ]
    for f in optional_files:
        check_file(f, required=False)
    
    print()
    
    # Check .env should NOT be in git
    print("🔒 Security Check:")
    if Path(".env").exists():
        print(f"  {GREEN}✓{RESET} .env exists locally (good - will not be committed)")
    else:
        print(f"  {YELLOW}⚠{RESET} .env not found - you'll need to set env vars in Railway")
    
    if Path(".gitignore").exists():
        with open(".gitignore") as f:
            content = f.read()
            if ".env" in content:
                print(f"  {GREEN}✓{RESET} .env in .gitignore (good)")
            else:
                print(f"  {RED}✗{RESET} .env NOT in .gitignore (add it!)")
                all_good = False
    
    print()
    
    # Check .env.example has all required vars
    print("🔑 Environment Variables Template (.env.example):")
    required_env_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_PHONE",
        "GROQ_API_KEY",
        "NVIDIA_API_KEY",
        "TAVILY_API_KEY",
        "STARTING_BALANCE",
        "TRADING_PAIRS",
    ]
    
    env_example = {}
    if Path(".env.example").exists():
        with open(".env.example") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _ = line.split("=", 1)
                    env_example[key.strip()] = _.strip()
        
        for var in required_env_vars:
            if not check_env_var(var, env_example):
                all_good = False
    else:
        print(f"  {RED}✗{RESET} .env.example not found")
        all_good = False
    
    print()
    
    # Check requirements.txt has key packages
    print("📦 Dependencies (requirements.txt):")
    required_packages = [
        "ccxt",
        "pandas",
        "numpy",
        "groq",
        "telethon",
        "python-dotenv",
        "requests",
    ]
    
    if Path("requirements.txt").exists():
        with open("requirements.txt") as f:
            content = f.read().lower()
            for pkg in required_packages:
                exists = pkg.lower() in content
                status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
                print(f"  {status} {pkg}")
                if not exists:
                    all_good = False
    else:
        print(f"  {RED}✗{RESET} requirements.txt not found")
        all_good = False
    
    print()
    
    # Check railway.json config
    print("⚙️ Railway Configuration (railway.json):")
    if Path("railway.json").exists():
        import json
        with open("railway.json") as f:
            try:
                config = json.load(f)
                if "deploy" in config and "startCommand" in config["deploy"]:
                    print(f"  {GREEN}✓{RESET} startCommand configured")
                    print(f"       → {config['deploy']['startCommand']}")
                else:
                    print(f"  {RED}✗{RESET} startCommand not found")
                    all_good = False
            except json.JSONDecodeError:
                print(f"  {RED}✗{RESET} Invalid JSON")
                all_good = False
    else:
        print(f"  {RED}✗{RESET} railway.json not found")
        all_good = False
    
    print()
    
    # Check Procfile
    print("📝 Procfile:")
    if Path("Procfile").exists():
        with open("Procfile") as f:
            content = f.read().strip()
            if "worker:" in content or "python" in content:
                print(f"  {GREEN}✓{RESET} Worker command found")
                print(f"       → {content}")
            else:
                print(f"  {YELLOW}⚠{RESET} Procfile exists but may be incorrect")
    else:
        print(f"  {RED}✗{RESET} Procfile not found")
        all_good = False
    
    print()
    print("="*60)
    
    if all_good:
        print(f"\n{GREEN}✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT!{RESET}\n")
        print("Next steps:")
        print("  1. Commit all files to Git (EXCEPT .env)")
        print("  2. Push to GitHub")
        print("  3. Deploy from GitHub in Railway Dashboard")
        print("  4. Set environment variables in Railway")
        print("  5. Monitor logs for errors\n")
        return 0
    else:
        print(f"\n{RED}❌ SOME CHECKS FAILED - FIX ISSUES BEFORE DEPLOYING{RESET}\n")
        print("Review the errors above and fix them before deploying.\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
