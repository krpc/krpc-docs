# Publish the Java client to Maven Central

The Java client is released only as a jar on GitHub (`krpc-java-X.Y.Z.jar`). It is not on Maven Central, so a Gradle or Maven project cannot declare it as a dependency. Every other client is published to its language's registry by a step in `tools/release/`: PyPI, NuGet, LuaRocks, vcpkg and the Arduino library index.

A user today downloads the jar and its two dependencies by hand, at versions that match the ones the client was built against, and puts all three on the class path. The client guide shows a plain `javac` command line for this.

With the client on Maven Central, a project needs one line, and its build tool fetches the dependencies:

```kotlin
dependencies { implementation("io.github.krpc:krpc-java:0.8.0") }
```

Proposal:

| Step | Detail |
|---|---|
| Namespace | Done: `io.github.krpc` is registered on the Central Portal and verified through the `krpc` GitHub organization (2026-10-29). |
| Artifact | `io.github.krpc:krpc-java`, with a POM declaring `com.google.protobuf:protobuf-java` and `org.javatuples:javatuples` at the versions in `MODULE.bazel`. |
| Build | `java_export` from `rules_jvm_external`, already a dependency, builds the jar, the POM, and the sources and javadoc jars Central requires. |
| Signing | A GPG key for the project, held with the other release credentials (`tools/release/release-credentials.toml.template`). |
| Release | A `tools/release/6x-release-maven.py` step, after the GitHub release, that uploads the signed bundle to the Central Portal. |
| Docs | The Java client guide leads with the Gradle and Maven coordinates, and keeps the jar download for builds without either. |

The POM pins protobuf-java at the version the client is built against. protobuf-java rejects generated code from a newer protobuf release at load time, so the dependency range matters more than for javatuples.

A Maven Central release cannot be deleted or replaced, so the first upload should be a release, not a test of the pipeline. The Central Portal has a validation step that can check a bundle without publishing it.

Publishing to a new registry needs a changelog entry.
