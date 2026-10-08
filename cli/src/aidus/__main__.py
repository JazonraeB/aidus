"""Command-line entry point: `aidus <command>` or `python -m aidus <command>`."""
import argparse
import sys

from . import __version__, SPEC_VERSION, commands


def build_parser():
    parser = argparse.ArgumentParser(prog="aidus", description=f"AIDUS {SPEC_VERSION} writer and validator.")
    parser.add_argument("--version", action="version", version=f"aidus {__version__} (AIDUS {SPEC_VERSION})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create .ai-usage/ in a repository")
    p.add_argument("--path", default=".", help="repository root (default: current directory)")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument("--hooks", action="store_true",
                   help="also install the prepare-commit-msg hook that adds AI-Session / Feature trailers")
    p.set_defaults(func=commands.cmd_init)

    p = sub.add_parser("record", help="append usage events read from an agent")
    p.add_argument("--from", dest="source", required=True, choices=["claude-code", "claude-code-hook"],
                   help="'claude-code-hook' reads the hook payload from stdin and never fails")
    p.add_argument("--transcript", help="transcript .jsonl (with --from claude-code)")
    p.add_argument("--project", default=".", help="path inside the repository (default: current directory)")
    p.set_defaults(func=commands.cmd_record)

    p = sub.add_parser("validate", help="check .ai-usage/ against the spec (use before committing)")
    p.add_argument("--path", default=".", help="path inside the repository (default: current directory)")
    p.set_defaults(func=commands.cmd_validate)

    p = sub.add_parser("session", help="track an agent session so commits get AI-Session trailers")
    p.add_argument("action", choices=["start", "end"])
    p.add_argument("--from", dest="source", choices=["claude-code-hook", "manual"], default="manual",
                   help="'claude-code-hook' reads the hook payload from stdin and never fails")
    p.add_argument("--session-id")
    p.add_argument("--path", default=".", help="path inside the repository")
    p.set_defaults(func=commands.cmd_session)

    p = sub.add_parser("trailers", help="(prepare-commit-msg hook) add AI-Session / Feature trailers")
    p.add_argument("message_file", nargs="?")
    p.add_argument("source", nargs="?", help="commit message source, as git passes it")
    p.set_defaults(func=commands.cmd_trailers)

    p = sub.add_parser("rebuild", help="regenerate usage.json from events/")
    p.add_argument("--path", default=".", help="path inside the repository (default: current directory)")
    p.set_defaults(func=commands.cmd_rebuild)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
