# Diagrams

Use Mermaid for architecture and flow diagrams. Write the source in ` ```mermaid ` fenced code blocks — GitHub renders these natively.

For universal rendering (outside GitHub), we convert diagrams to images via **mermaid.ink** — a public web service that renders Mermaid source into SVGs. The conversion script base64-encodes the Mermaid source and embeds it as an image URL.

**IMPORTANT: Never send confidential information to mermaid.ink.** The Mermaid source is transmitted to a third-party server. Diagrams must NOT contain:
- AWS account IDs, API keys, or credentials
- Internal hostnames, IP addresses, or endpoint URLs
- Customer data or PII
- Proprietary business logic details

Generic architecture diagrams (service names, data flows, table names) are fine. If a diagram contains anything sensitive, keep it as a ` ```mermaid ` block (GitHub-only rendering) and do NOT convert it to a mermaid.ink URL.
