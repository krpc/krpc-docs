"""Run the Python client guide examples against the game."""

import os
import subprocess
import sys
import time
import unittest

import krpctest

SCRIPTS = os.path.join(
    os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd()),
    "doc/src/scripts/python/client",
)


def start(name):
    return subprocess.Popen(
        [sys.executable, "-u", os.path.join(SCRIPTS, name)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish(proc, timeout):
    """Wait for the script, killing it at the timeout. Returns (exited, stdout, stderr)."""
    try:
        out, err = proc.communicate(timeout=timeout)
        return True, out, err
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return False, out, err


def report(name, exited, code, out, err):
    lines = out.splitlines()
    print(
        "\n=== %s exited=%s code=%s lines=%d\n%s\n--- stderr\n%s"
        % (name, exited, code, len(lines), "\n".join(lines[:6]), err[-1500:])
    )


class Base(krpctest.TestCase):
    def run_script(self, name, timeout=10, expect_exit=True, during=None):
        proc = start(name)
        if during is not None:
            time.sleep(4)
            during()
        exited, out, err = finish(proc, timeout)
        report(name, exited, proc.returncode, out, err)
        self.assertNotIn("Traceback", err)
        if expect_exit:
            self.assertTrue(exited, "did not exit")
            self.assertEqual(0, proc.returncode)
        else:
            self.assertFalse(exited, "exited early")
        return out


class TestInOrbit(Base):
    @classmethod
    def setUpClass(cls):
        cls.new_save()
        cls.launch_vessel_from_vab("Basic")
        cls.remove_other_vessels()
        cls.set_circular_orbit("Kerbin", 100000)
        cls.vessel = cls.connect().space_center.active_vessel

    def tearDown(self):
        self.vessel.control.abort = False

    def test_one_shot(self):
        for name in [
            "Connecting1.py",
            "Connecting3.py",
            "CompileDecorator.py",
            "CompiledFunctionArguments.py",
            "CompiledStatements.py",
            "Errors.py",
            "NotLoadedStream.py",
            "RemoteObjects.py",
            "RemoteProcedures.py",
            "RunFunction.py",
            "StateVariable.py",
            "StreamRate.py",
            "Threads.py",
            "Event.py",
            "CompiledEvent.py",
        ]:
            with self.subTest(name):
                self.run_script(name)

    def test_connecting_local(self):
        self.run_script("ConnectingLocal.py")

    def test_loops(self):
        for name in [
            "CompiledFunction.py",
            "CompiledFunctionStream.py",
            "EventCallback.py",
            "Streaming1.py",
            "Streaming2.py",
            "Streaming3.py",
            "Streaming4.py",
        ]:
            with self.subTest(name):
                out = self.run_script(name, timeout=5, expect_exit=False)
                self.assertTrue(out.strip(), "no output")

    def test_callbacks(self):
        def abort():
            self.vessel.control.abort = True

        out = self.run_script("Callbacks.py", timeout=8, expect_exit=False, during=abort)
        self.assertIn("Abort 1 called with a value of True", out)
        self.assertIn("Abort 2 called with a value of True", out)

    def test_condition_variables(self):
        def abort():
            self.vessel.control.abort = True

        self.run_script("ConditionVariables.py", timeout=10, during=abort)


class TestOnPad(Base):
    @classmethod
    def setUpClass(cls):
        cls.new_save()

    def setUp(self):
        self.launch_vessel_from_vab("Basic")
        self.remove_other_vessels()

    def test_stream_end(self):
        out = self.run_script(
            "StreamEnd.py",
            timeout=20,
            during=lambda: self.launch_vessel_from_vab("Basic"),
        )
        self.assertIn("The part was destroyed", out)

    def test_end_callback(self):
        out = self.run_script(
            "EndCallback.py",
            timeout=12,
            expect_exit=False,
            during=lambda: self.launch_vessel_from_vab("Basic"),
        )
        self.assertIn("The stream ended:", out)


if __name__ == "__main__":
    unittest.main()
