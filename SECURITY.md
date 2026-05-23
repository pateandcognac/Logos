# Security

This is a hobby/research robot workspace for one physical robot. Please do not
expect a production security program, but responsible reports are welcome.

## Reporting

Open a private advisory on GitHub if available, or contact the repository owner
through the public profile. Avoid posting working exploits, credentials, or
private data in public issues.

## Scope

Useful reports include:

- exposed credentials or private keys;
- code paths that could unexpectedly command robot motion;
- unsafe assumptions around filesystem or shell access;
- public files that appear to contain personal logs, captures, or memory;
- dependency or launch patterns that create unnecessary network exposure.

## Credentials

Runtime credentials must be supplied through environment variables. Do not
commit `.env` files, API keys, tokens, certificates, or private keys.

## Physical Safety

This code can control a real mobile robot. Treat motion, speech, sensors, and
shell access as physical-world capabilities, not abstract demo functions.
