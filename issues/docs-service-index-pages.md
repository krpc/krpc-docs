# Docs: service index pages with an example, the service's name in each client, and no "API" suffix

Each service in the API docs has an index page (`doc/api/<service>.tmpl`) that links to its class
pages. These pages are uneven, and they are the first page a new user reaches for a service.

* **Titles end in "API"**: "KRPC API", "User Interface API", "Debug API". The suffix adds nothing
  inside the API reference. "Standard Library", "SpaceCenter API" and "LIDAR API" are already
  inconsistent with each other.
* **Some pages are a list of links.** InfernalRobotics, Kerbal Alarm Clock, LIDAR and RemoteTech
  have a short example. Debug, Docking Camera and Kerbal Engineer Redux have a sentence. Drawing,
  KRPC, SpaceCenter and User Interface have only the links.
* **The page does not say how to reach the service from a client.** Nothing maps
  `InfernalRobotics` to `conn.infernal_robotics` in Python, `conn.InfernalRobotics()` in C#, or
  the service object in C++ and Java. The Python guide states the rule once, for `space_center`.
  Users of the mod services have to guess.
* **A small service is split across two pages.** "Debug API" is a sentence and one link, and the
  API itself is on "Debug API -> Debug". Docking Camera and LIDAR have two subpages each.

Proposal:

| Change | Detail |
| --- | --- |
| Drop "API" from the titles | Each index page is titled with the service's display name, e.g. "Debug", "User Interface" |
| A sentence and an example on every index page | What the service is for, then a short example per client language that gets the service from the connection and makes one call. The example shows the service's name in the reader's client |
| One page for a small service | A service with one class page or none, such as Debug, puts its members on the index page. The threshold is a judgment call, e.g. under a screen of members |

* Examples go in `doc/src/scripts/api/<service>/`, as the existing ones do, so the build compiles
  and checks them.
* A title change moves no URLs. Merging a subpage into its index removes the subpage's URL, and
  the docs build has no redirects, so links to it break.

Labels: `enhancement`, `docs`.
