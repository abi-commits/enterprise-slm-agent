#!/usr/bin/env python
"""
Validation script to check project setup and dependencies before testing.
Run this before running integration tests to validate the environment.
"""

import sys
import subprocess
from pathlib import Path


class Validator:
    """System validator for the SLM-First project."""
    
    def __init__(self):
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []
    
    def check_python_version(self):
        """Check Python version is 3.11+."""
        print("Checking Python version...", end=" ")
        version = sys.version_info
        if version.major >= 3 and version.minor >= 11:
            print(f"✓ (Python {version.major}.{version.minor}.{version.micro})")
            self.checks_passed.append("Python version")
        else:
            print(f"✗ (Python {version.major}.{version.minor} - requires 3.11+)")
            self.checks_failed.append("Python version")
    
    def check_dependencies(self):
        """Check that required packages are installed."""
        print("Checking dependencies...", end=" ")
        required_packages = [
            "fastapi",
            "pydantic",
            "pytest",
            "httpx",
            "qdrant_client",
            "sentence_transformers",
        ]
        
        missing = []
        for package in required_packages:
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing.append(package)
        
        if not missing:
            print("✓")
            self.checks_passed.append("Dependencies")
        else:
            print(f"✗ (Missing: {', '.join(missing)})")
            self.checks_failed.append(f"Dependencies: {', '.join(missing)}")
    
    def check_project_structure(self):
        """Check project directory structure."""
        print("Checking project structure...", end=" ")
        required_dirs = [
            "services/api",
            "services/knowledge",
            "services/inference",
            "core",
            "tests",
        ]
        
        missing = []
        for directory in required_dirs:
            if not Path(directory).exists():
                missing.append(directory)
        
        if not missing:
            print("✓")
            self.checks_passed.append("Project structure")
        else:
            print(f"✗ (Missing: {', '.join(missing)})")
            self.checks_failed.append(f"Project structure: {', '.join(missing)}")
    
    def check_docker_compose(self):
        """Check Docker Compose configuration."""
        print("Checking Docker Compose...", end=" ")
        if Path("docker-compose.yml").exists():
            print("✓")
            self.checks_passed.append("Docker Compose")
        else:
            print("✗ (docker-compose.yml not found)")
            self.checks_failed.append("Docker Compose file")
    
    def check_env_file(self):
        """Check environment configuration."""
        print("Checking environment setup...", end=" ")
        if Path(".env").exists():
            print("✓ (.env file found)")
            self.checks_passed.append("Environment file")
        elif Path(".env.example").exists():
            print("⚠ (.env.example found, copy to .env for local setup)")
            self.warnings.append("Environment file: Copy .env.example to .env")
        else:
            print("✗ (No .env or .env.example found)")
            self.checks_failed.append("Environment file")
    
    def check_docker_running(self):
        """Check if Docker is running."""
        print("Checking Docker service...", end=" ")
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                timeout=5,
                text=True
            )
            if result.returncode == 0:
                print("✓")
                self.checks_passed.append("Docker service")
            else:
                print("✗ (Docker not responding)")
                self.checks_failed.append("Docker service not responding")
        except FileNotFoundError:
            print("✗ (Docker not installed)")
            self.checks_failed.append("Docker not installed")
        except subprocess.TimeoutExpired:
            print("✗ (Docker service timeout)")
            self.checks_failed.append("Docker service timeout")
    
    def check_pytest_config(self):
        """Check pytest configuration."""
        print("Checking pytest configuration...", end=" ")
        try:
            result = subprocess.run(
                ["pytest", "--co", "-q", "tests/"],
                capture_output=True,
                timeout=10,
                text=True
            )
            if result.returncode == 0:
                test_count = len([l for l in result.stdout.split("\n") if "test_" in l])
                print(f"✓ ({test_count} tests found)")
                self.checks_passed.append("Pytest configuration")
            else:
                print("✗ (Couldn't collect tests)")
                self.checks_failed.append("Pytest configuration")
        except subprocess.TimeoutExpired:
            print("✗ (Pytest collection timeout)")
            self.checks_failed.append("Pytest collection")
    
    def check_services_running(self):
        """Check if required services are running."""
        print("Checking services...", end=" ")
        services_to_check = {
            "postgres": ("postgres:16", "Database"),
            "redis": ("redis:7", "Cache"),
            "qdrant": ("qdrant:latest", "Vector DB"),
            "vllm": ("vllm:latest", "Inference"),
        }
        
        try:
            result = subprocess.run(
                ["docker-compose", "ps", "--services"],
                capture_output=True,
                timeout=10,
                text=True
            )
            if result.returncode == 0:
                running = result.stdout.strip().split("\n")
                missing = [name for name in services_to_check if name not in running]
                if not missing:
                    print("✓ (All services running)")
                    self.checks_passed.append("Services running")
                else:
                    print(f"⚠ (Services not running: {', '.join(missing)})")
                    self.warnings.append(f"Services not running: {', '.join(missing)}")
            else:
                print("⚠ (Docker Compose not initialized)")
                self.warnings.append("Docker Compose services not running - run 'make up'")
        except FileNotFoundError:
            print("⚠ (Docker Compose not found)")
            self.warnings.append("Docker Compose not available")
        except subprocess.TimeoutExpired:
            print("⚠ (Docker Compose timeout)")
            self.warnings.append("Docker Compose timeout")
    
    def run_all_checks(self):
        """Run all validation checks."""
        print("\n" + "=" * 60)
        print("SLM-First Project Validation")
        print("=" * 60 + "\n")
        
        self.check_python_version()
        self.check_dependencies()
        self.check_project_structure()
        self.check_docker_compose()
        self.check_env_file()
        self.check_docker_running()
        self.check_pytest_config()
        self.check_services_running()
        
        return self.print_summary()
    
    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("Validation Summary")
        print("=" * 60)
        
        if self.checks_passed:
            print(f"\n✓ Passed ({len(self.checks_passed)}):")
            for check in self.checks_passed:
                print(f"  - {check}")
        
        if self.warnings:
            print(f"\n⚠ Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if self.checks_failed:
            print(f"\n✗ Failed ({len(self.checks_failed)}):")
            for check in self.checks_failed:
                print(f"  - {check}")
        
        print("\n" + "=" * 60)
        
        if self.checks_failed:
            print("Status: ✗ VALIDATION FAILED")
            print("Please fix the issues above before running tests.\n")
            return 1
        elif self.warnings:
            print("Status: ⚠ VALIDATION PASSED WITH WARNINGS")
            print("Tests can run, but some optional checks failed.\n")
            return 0
        else:
            print("Status: ✓ VALIDATION PASSED")
            print("System is ready for testing.\n")
            return 0


def main():
    """Run the validator."""
    validator = Validator()
    exit_code = validator.run_all_checks()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
