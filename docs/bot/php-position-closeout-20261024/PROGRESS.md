# P-20261024-004 omitnix: request entry

Instructions: README.md, FACTS.md, REVIEW.md in this directory.
The local conductor owns this file. Dots must not edit it.

Current phase: acknowledged; bot has public read access but no write permission and no
tool to accept its repository invitation. The local conductor has taken over code
changes. Dots continues independent public-source review without switching accounts.
Management issue: https://github.com/ishizakahiroshi/omitnix/issues/14

Local validation has confirmed the C2 production change and identified a generic-test
skip weakness for repair. Experimental rewrite compatibility is being checked locally.
Python integration, clean-fixture golden acceptance, main CI and PyPI remain pending.

Required acceptance: code submission from the bot identity; independent review of the
submitted SHA; focused and full local Python checks; tracked-only golden acceptance;
separate local experimental-rewrite compatibility checks; main PR checks and merge;
Python package build, tag-driven PyPI publication and isolated installed-wheel smoke
test. The conductor owns integration and publication. Dots completion alone does not
complete this parent task. Status changes and evidence belong in the management issue.
