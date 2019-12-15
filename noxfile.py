from xml.etree import ElementTree as ET
import os
import re
import shutil

import nox


source_code = ("src/", "tests/", "docs/", "setup.py", "noxfile.py")


def _clean_coverage(coverage_path):
    input_xml = ET.ElementTree(file=coverage_path)
    for class_ in input_xml.findall(".//class"):
        filename = class_.get("filename")
        filename = re.sub("_sync", "_async", filename)
        class_.set("filename", filename)
    input_xml.write(coverage_path, xml_declaration=True)


def tests_impl(session):
    # Install deps and the package itself.
    session.install("-r", "dev-requirements.txt")
    session.install(".")

    # Show the pip version.
    session.run("pip", "--version")
    # Print the Python version and bytesize.
    session.run("python", "--version")
    session.run("python", "-c", "import struct; print(struct.calcsize('P') * 8)")

    session.run(
        "pytest",
        "-r",
        "a",
        "--tb=native",
        "--cov=hip",
        "--no-success-flaky-report",
        *(session.posargs or ("tests/",)),
        env={"PYTHONWARNINGS": "always::DeprecationWarning"}
    )
    session.run("coverage", "xml")
    _clean_coverage("coverage.xml")


@nox.session(python=["3.6", "3.7", "3.8"])
def test(session):
    tests_impl(session)


@nox.session()
def blacken(session):
    """Run black code formatter."""
    session.install("black")
    session.run("black", *source_code)

    lint(session)


@nox.session
def lint(session):
    session.install("flake8", "black")
    session.run("flake8", "--version")
    session.run("black", "--version")
    session.run("black", "--check", *source_code)
    session.run("flake8", *source_code)


@nox.session
def docs(session):
    session.install("-r", "docs/requirements.txt")

    session.chdir("docs")
    if os.path.exists("_build"):
        shutil.rmtree("_build")
    session.run("sphinx-build", "-W", ".", "_build/html")
