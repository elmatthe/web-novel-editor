Read AI-WORKSPACE.md and all permanent md-instructions documents in the required kickoff
order, then read md-instructions/Instructions_Phase10_JunkStrip_And_QA.md completely.

Implement the plan exactly in its documented Phase 0 through Phase 11 order. Begin with
the read-only repository inspection and baseline safety snapshot. Preserve all local,
ignored, untracked, and modified files; do not use destructive Git cleanup commands.

Work on feature/junk-strip-hardening, creating it from the verified current main branch
only after inspecting the current branch, HEAD, status, remote state, and whether that
feature branch already exists.

Treat the two local corpora under files/test-files/ as copyrighted, local-only QA inputs.
Never modify them, force-add them, write generated output into their folders, or commit
full extracted chapter text.

Follow every checkpoint, testing requirement, commit boundary, documentation update, and
acceptance criterion in the instruction file. Do not silently broaden editorial rules,
GUI scope, PDF deletion behavior, platform-support claims, dependencies, or release
contents beyond what evidence and the plan justify.

The plan intentionally requires a user decision in Phase 8 §5 if build-spec.md conflicts
with AI-WORKSPACE.md over relocating runtime-required novel resources from files/ into
the shipped scripts/Universal resource tree. Stop at that specific decision and report
the discovered runtime dependencies and your recommended destination before moving them.

Do not merge to main. Delete the temporary instruction markdown only at the point directed
by Phase 11, after permanent documentation has been finalized and before the final
official verification runs. Leave the completed feature branch ready for review.