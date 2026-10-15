# PhysicsBank notices

The single-screenshot figure-slot/crop protocol, manual-crop editor and regression
tests adapt selected code from MathBank commit
`3252b7237f3add8f632f00a413a23814ed8882a4`, contributed by JudgePeach.
PhysicsBank keeps physics prompts and a source-crop-first, teacher-review workflow;
it does not enable the upstream automatic paid visual-review loop.

PhysicsBank is a modified version of
[JudgePeach/math-question-bank](https://github.com/JudgePeach/math-question-bank),
originally distributed under the GNU Affero General Public License version 3.

Copyright for the original work remains with its original contributors.
The PhysicsBank changes add a high-school physics curriculum, physics-oriented
AI prompts, physics question types, interface wording, and physics paper export
defaults.

PhysicsBank is distributed under the same GNU AGPL-3.0 license. See `LICENSE`.
The codebase also incorporates upstream MathBank changes through commit
`adbc2df` (MathBank 2.4.0 plus later main-branch commits), while retaining
the original repository history.

Additional selected upstream preview and release-boundary fixes have been adapted with
physics-specific regression checks. Their source commits and remaining
unported changes are recorded in `docs/upstream-sync.md`; this does not
represent a complete upgrade to the latest MathBank release.

The upright-constant preview, startup knowledge preservation and
maintenance-tool release isolation changes
adapt selected portions of upstream commits `3252b72` and `550b319`, authored
by JudgePeach. Their adoption does not imply the OCR or schema changes from
MathBank 2.7.0 are included. Source-only tools remain available in this source
repository; they are excluded from portable runtime packages.
