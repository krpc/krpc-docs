# Docs: refresh the third-party projects page

`doc/src/third-party.rst` lists clients, scripts and tools that other people made for kRPC. The
home page cards and the clients toctree link to it. It is the place people find a client in a
language kRPC does not ship, so it stays. Its content has gone stale:

* `//doc:linkcheck` catches dead links, not projects that are abandoned or no longer work with the
  current version.
* Some entries look abandoned: the kIPC forum thread is from KSP 1.1.3, and the F# snippet is old.
  The Node.js client predates the official one in the plan.
* The page asks people to request a listing on a forum thread titled for kRPC v0.6.0.
* A listing in the docs reads as an endorsement, and nothing says otherwise.

## Proposal

* Open the page with a note: these are community projects, not maintained by kRPC, and may not
  support the current version.
* Take listings as pull requests to the page, or on Discord, in place of the forum thread.
* Prune once: check each project's last activity and its support for the current protocol. Drop
  the dead or superseded ones.
* Add a "last reviewed" date, so a reader can judge how fresh the list is.

## Alternative

Move the list to a community-editable place, GitHub Discussions or the wiki, and link it from the
docs. It moves the upkeep to the authors, but the projects are no longer found by searching the
docs.
