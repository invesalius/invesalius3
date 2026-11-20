# Changelog Contribution Guidelines

This document provides guidelines for maintaining InVesalius's CHANGELOG.

## When to Update the CHANGELOG

You should update the CHANGELOG when making changes that affect users:

- ✅ **DO** update for new features
- ✅ **DO** update for bug fixes  
- ✅ **DO** update for breaking changes
- ✅ **DO** update for dependency updates
- ✅ **DO** update for performance improvements
- ❌ **DON'T** update for internal refactoring (unless it affects users)
- ❌ **DON'T** update for test-only changes
- ❌ **DON'T** update for documentation typo fixes

## Format

We follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

### Categories

Use these standard categories in order:

- **Added** - New features
- **Changed** - Changes to existing functionality
- **Deprecated** - Soon-to-be removed features
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Security vulnerability fixes
- **DevOps** - CI/CD, build, and deployment improvements
- **Dependencies** - External library updates

## How to Write Changelog Entries

### Good Entry Examples

✅ **Good:**
```markdown
- Added support for TIFF image import with transparency
- Fixed crash when loading DICOM files with non-ASCII characters
- Updated wxPython from 4.1.0 to 4.2.0 for better macOS compatibility
```

### Bad Entry Examples

❌ **Bad:**
```markdown
- Fixed bug (too vague)
- Refactored code (internal change, not user-facing)
- Updated stuff (not specific enough)
```

### Writing Guidelines

1. **Be specific** - Describe what changed, not just that something changed
2. **User-focused** - Write from the user's perspective
3. **Action-oriented** - Start with a verb (Added, Fixed, Updated, etc.)
4. **Concise** - One line per entry when possible
5. **Reference issues** - Link to issue numbers when applicable: `(#123)`

## Where toAdd Entries

Always add new entries to the **[Unreleased]** section at the top of `changelog.md`.

```markdown
## [Unreleased]

### Added
- Your new feature here

### Fixed
- Your bug fix here
```

When a new version is released, the maintainers will:
1. Rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`
2. Create a new empty `[Unreleased]` section
3. Update version links at the bottom

## Example Entry

If you fixed issue #1064 about a crash on language dialog cancellation:

```markdown
## [Unreleased]

### Fixed
- Fixed crash when cancelling Language Selection dialog on first run (#1064)
```

## Pull Request Checklist

When submitting a PR:

- [ ] Updated CHANGELOG under appropriate category
- [ ] Entry is user-focused and descriptive
- [ ] Entry is in the `[Unreleased]` section
- [ ] Referenced the issue number if applicable

## Questions?

If you're unsure whether your change warrants a CHANGELOG entry, ask yourself:

> "Would a user want to know about this change?"

If yes, add it to the CHANGELOG!

---

**Last updated:** 2026-01-23
