"""The domain core.

Deliberately free of the Strands SDK, of boto3 and of every network call. The
agent decides; this package calculates. Everything here runs offline, which is
what lets the test suite prove the numbers without a key.
"""
