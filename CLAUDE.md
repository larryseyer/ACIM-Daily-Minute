# ACIM Daily Minute - Claude Code Project Notes

## Remote Development Environment

**Claude runs on**: M4 Mac (remote)
**Project files on**: 2012 Intel Mac running macOS Catalina

### Path Mapping

| Context | Path |
|---------|------|
| Remote (Claude sees) | `/Volumes/MacLive/Users/larryseyer/acim-daily-minute` |
| Local (user runs) | `/Users/larryseyer/acim-daily-minute` |

### Critical Rules

1. **File operations**: Use `/Volumes/MacLive/...` paths for Read/Write/Edit tools
2. **User commands**: Always give paths as `/Users/larryseyer/...` when instructing user to run commands locally
3. **Python execution**: Claude CANNOT run Python scripts - they must run on the Intel Mac
4. **venv**: Virtual environments must be created locally on the Intel Mac (different Python versions/architectures between machines)
5. **Serena MCP**: Does NOT work on this remote setup - use Claude Code native tools only

### Python Environment

- Intel Mac (Catalina): Python 3.8 or 3.9
- M4 Mac: Python 3.13
- Always have user recreate venv locally when needed
