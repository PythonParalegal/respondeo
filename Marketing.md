# Respondeo — Commercialization Guide

> **Document Classification:** Confidential — Business Strategy
> **Author:** Respondeo maintainer
> **Last Updated:** March 2026

---

## Market Opportunity

Small and mid-size law firms currently face a lose-lose choice for e-discovery: pay exorbitant per-GB vendor fees that scale with every case, or attempt manual document review that burns paralegal hours and creates defensibility risk. There is no affordable, self-hosted, full-lifecycle e-discovery product targeting the 2–20 attorney firm segment.

Respondeo fills that gap.

---

## Competitive Landscape & Pricing

### What Firms Pay Today

| Platform | Pricing Model | Estimated Cost |
|----------|--------------|----------------|
| **Relativity** | Per-GB storage + per-user license | ~$15/GB/month + $100/user/month |
| **Everlaw** | Per-GB cloud storage, unlimited users | $7–18/GB/month (varies by data tier) |
| **DISCO** | Flat per-GB, all-inclusive | Undisclosed flat rate; no user fees |
| **Logikcull** | Monthly base + per-GB processing | $199/month base + $25/GB processing |
| **Full-Service Vendor** | Processing + hosting + review + production | $25–75+/GB combined |

### Real-World Cost Example

A firm handling a **moderate commercial litigation matter** with 25GB of collected data:

| Scenario | Year 1 Cost | Ongoing |
|----------|-------------|---------|
| **Relativity** (self-hosted) | $4,500/mo hosting + $300/mo users = ~$57,600/yr | Same |
| **Everlaw** | 25GB × $18/GB/mo = $5,400/yr (active data) | Same while case is open |
| **Full-Service Vendor** | 25GB × $50/GB = $1,250 processing + $375/mo hosting = ~$5,750/yr | Hosting continues |
| **Respondeo** | $12,000–$18,000 (license + setup) | $8,000–$12,000/yr |

**Key differentiator:** The Hub's cost is **fixed regardless of data volume.** A 5GB case and a 500GB case cost the same. This eliminates the most painful aspect of vendor pricing — the anxiety of not knowing what the bill will be until the data arrives.

---

## Revenue Streams

### Primary: Software License

| Model | Price Range | Notes |
|-------|------------|-------|
| **Annual license per firm** | $8,000–$15,000/year | Covers unlimited cases, unlimited data, unlimited users |
| **One-time perpetual license** | $20,000–$35,000 | Higher upfront, no renewals (consider offering with optional support contract) |

> [!TIP]
> **Start with annual licensing.** It creates predictable recurring revenue and gives you leverage to push updates and improvements. Perpetual licenses should be priced at 2–3× the annual fee.

### Secondary: Professional Services

| Service | Price Range | Frequency |
|---------|------------|-----------|
| **Installation & setup** | $3,000–$5,000 | One-time per firm |
| **Staff training** | $1,500–$3,000 | Per session (2–4 hours) |
| **Custom configuration** | $150–$250/hour | As-needed consulting |
| **On-call support** | $200–$400/month | Optional retainer |
| **Upgrade deployment** | $500–$1,000 | Per major version |

### Tertiary: Premium Features (Future)

| Feature | Model |
|---------|-------|
| **Search Term Reports (STR)** | Included or add-on depending on tier |
| **Multi-case dashboard** | Premium tier |
| **Active Directory/SSO integration** | Enterprise tier |
| **Automated privilege log generation** | Add-on |
| **Automated progress reporting** | Add-on |

---

## Your Cost Structure

### Startup Costs (One-Time)

| Item | Estimated Cost | Notes |
|------|---------------|-------|
| **PyMuPDF commercial license** | Contact Artifex — likely $2,000–$8,000/year | OEM/redistribution license; per-copy with quarterly minimums. One license covers all deployments of your product. Contact `sales@artifex.com`. | <!-- pii-guard: allow (public vendor contact) -->
| **Code signing certificate** | $210–$620/year | Sectigo OV: ~$210/yr; DigiCert EV: ~$500–620/yr. Required to avoid Windows SmartScreen warnings. EV recommended for professional impression. |
| **Business formation** | $500–$2,000 | LLC or similar entity. Consult your own attorney. |
| **Professional liability insurance** | $1,000–$3,000/year | E&O / tech errors coverage. Consider this essential when distributing software that handles privileged legal data. |
| **Domain + basic web presence** | $200–$500/year | Marketing site, documentation hosting |

### Per-Sale Marginal Cost

| Item | Cost | Notes |
|------|------|-------|
| **PyMuPDF per-copy fee** | TBD — clarify with Artifex | May be per-deployment or covered by OEM flat rate |
| **Your installation time** | 4–8 hours | Billable as professional services |
| **Ongoing support time** | 1–2 hours/month average | Covered by support retainer |

### Annual Operating Costs (Estimated)

| Item | Low End | High End |
|------|---------|----------|
| PyMuPDF license | $2,000 | $8,000 |
| Code signing certificate | $210 | $620 |
| Insurance | $1,000 | $3,000 |
| Web/marketing | $200 | $500 |
| **Total annual overhead** | **~$3,500** | **~$12,000** |

> [!IMPORTANT]
> **Break-even analysis:** At the low end ($3,500 overhead), a single client paying $10,000/year covers all costs with profit. Every additional client is nearly pure margin after your time investment.

---

## Distribution Model

### Self-Hosted Product (Recommended)

Each client receives the software and runs it on their own hardware. You are a **software vendor**, not a service provider.

**What you deliver:**
- Software package (ZIP or private Git repo access)
- Setup script (PowerShell) that installs Python, dependencies, OpenSearch
- Configuration walkthrough
- Training session
- Walkthrough.md as their reference documentation

**What the client provides:**
- Dedicated Windows PC or server (minimum: 16GB RAM, SSD, multi-core)
- Microsoft Office license (already have)
- Network access for browser-based review (internal only)

**Updates:**
- Delivered as new ZIP / `git pull` — client extracts and restarts the server
- Database and case folders are separate from application code, so updates never touch client data
- Major version updates can be delivered as a billable service call

**License Enforcement Options (choose one before first sale):**
- *Honor system* — simplest; trusts the client; best for early relationships
- *License key on startup* — adds enforcement but requires implementation
- *Annual re-delivery model* *(recommended)* — a lapsed license means the client is stuck on their current version; new versions require renewal. No phone-home required, no enforcement complexity, natural incentive to renew.

### Why Not SaaS

> [!CAUTION]
> **Do not offer this as a hosted/managed service.** The following risks are severe and potentially career-ending:

| Risk | Consequence |
|------|-------------|
| **Conflict of interest** | If two client firms are adversaries on a case, you have access to both sides' privileged work product. This is an irreconcilable ethical conflict that could result in disqualification of both firms. |
| **Custodian of privileged data** | You become a third-party custodian of attorney-client privileged material. Any breach, subpoena, or data incident exposes you to malpractice claims from every client simultaneously. |
| **State bar ethics rules** | Most jurisdictions impose strict rules on third-party vendors handling privileged material. Compliance obligations vary by state and are constantly evolving. |
| **Data sovereignty** | Law firms (especially those handling government contracts or family law) may be contractually prohibited from storing client data on third-party infrastructure. |
| **Liability concentration** | A single server failure, ransomware attack, or data breach affects every client. Self-hosted = each firm manages their own risk. |

**The self-hosted model eliminates all of these risks.** You sell software. They own their data. You never see a single document.

---

## Sales Positioning

### The Pitch (30-Second Version)

*"You know what you're paying [Vendor X] per gigabyte? What if that cost was zero — on every case, forever? Our platform does everything Relativity does for document processing, review, and production, but it runs on a single PC in your office. No vendor fees, no per-GB charges, no data leaving your building. It pays for itself on your first case."*

### Key Selling Points

| Point | Why It Resonates |
|-------|-----------------|
| **Zero per-GB cost** | Eliminates the most painful, unpredictable line item in litigation budgets |
| **Data stays in-house** | Critical for government work, family law, employment cases |
| **Unlimited users** | No per-seat licensing — every attorney and paralegal gets access |
| **No vendor dependency** | Firm controls their own timeline, no waiting for vendor processing queues |
| **Review hours saved** | Threading, near-dupe, and junk filtering recover 40–100+ paralegal hours per case |
| **Auto-generated privilege log** | One click generates a formatted privilege log from tagged documents — a deliverable paralegals dread doing manually |
| **Filevine integration** | Firms already using Filevine get seamless document sync and redaction workflow |
| **Browser-based** | No software install on reviewer workstations — IT loves this |
| **Built by a litigator** | Designed by a practicing attorney — chain of custody, Bates standards, and privilege protocols are baked in, not bolted on |

### Ideal Customer Profile

| Characteristic | Why |
|----------------|-----|
| 2–20 attorney firm | Large enough to have regular discovery, small enough that Relativity is overkill |
| Handles litigation with document-intensive discovery | Commercial disputes, employment, product liability, regulatory matters |
| **High-volume, fixed-fee practices** | Fixed-fee arrangements make per-GB pricing acutely painful; cost-consciousness is structural |
| Already uses Filevine | Immediate value from the sync integration |
| Cost-conscious / value-driven | Firm leadership that tracks overhead and seeks competitive advantages |
| Has one tech-capable person | Paralegal or office manager who can manage the server |

---

## Legal & Business Considerations

### Entity Structure

Form a separate LLC or similar entity for software sales. This separates your legal practice liability from product liability. Consult a business attorney for your jurisdiction.

### Contracts You'll Need

| Document | Purpose |
|----------|---------|
| **End-User License Agreement (EULA)** | Defines what the client can and cannot do with the software. Limits your liability. |
| **Software Support Agreement** | Terms for ongoing support, response times, update delivery |
| **Statement of Work (SOW)** | Scoped installation and training deliverables per engagement |
| **Limitation of Liability clause** | Critical: your liability should be limited to the license fee amount. You are not responsible for their data, their review decisions, or their production errors. |

### Insurance

- **Technology Errors & Omissions (E&O)** — covers claims arising from software defects
- **General Liability** — standard business coverage
- **Cyber Liability** — consider if you ever touch client data during installation/support

### Open-Source Compliance

| Library | License | Action Required |
|---------|---------|----------------|
| **PyMuPDF** | AGPL 3.0 | **Purchase commercial license from Artifex before any sale.** AGPL requires open-sourcing your entire codebase if distributed without a commercial license. |
| **OpenSearch** (server + client) | Apache 2.0 | ✅ No restrictions. This is a deliberate advantage over Elasticsearch, which moved to the restrictive Elastic License 2.0 in 2021. |
| **All others** | Apache 2.0 / MIT / BSD | No restrictions on commercial use. |

---

## Financial Projections (Conservative)

### Year 1: Validation

| Item | Amount |
|------|--------|
| Clients | 1–2 (pilot firms, possibly at a discounted rate) |
| License revenue | $8,000–$20,000 |
| Services revenue | $6,000–$10,000 |
| **Total revenue** | **$14,000–$30,000** |
| Operating costs | $5,000–$12,000 |
| **Net** | **$9,000–$18,000** |

### Year 2: Growth

| Item | Amount |
|------|--------|
| Clients | 3–6 (cumulative, including renewals) |
| License revenue | $24,000–$60,000 |
| Services revenue | $12,000–$25,000 |
| **Total revenue** | **$36,000–$85,000** |
| Operating costs | $8,000–$15,000 |
| **Net** | **$28,000–$70,000** |

### Year 3: Established

| Item | Amount |
|------|--------|
| Clients | 6–12 (cumulative) |
| License revenue | $48,000–$120,000 |
| Services revenue | $20,000–$40,000 |
| **Total revenue** | **$68,000–$160,000** |
| Operating costs | $10,000–$20,000 |
| **Net** | **$58,000–$140,000** |

> [!NOTE]
> These projections assume the product remains a side business alongside legal practice. If it becomes a primary focus, revenue growth could accelerate significantly with dedicated sales effort, but would also require more investment in support infrastructure.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Client has a bad experience** | Thorough installation testing, training documentation, responsive support. First 2 clients should be treated as beta partners with extra attention. |
| **Competitor launches similar product** | Your cost structure is nearly impossible to undercut. Enterprise competitors (Relativity, Everlaw) won't cannibalize their per-GB revenue model to compete at your price point. |
| **PyMuPDF changes licensing terms** | Monitor Artifex communications. If terms become unfavorable, replacement libraries exist (painful but possible). |
| **Client demands features you haven't built** | Scope clearly in the EULA. Custom development is billable consulting, not included in the license. |
| **Support burden grows faster than revenue** | Invest in documentation and self-service troubleshooting before scaling past 5 clients. Consider a knowledge base or FAQ portal. |
| **You accidentally see client data during install** | Establish a written policy: installations use test data only. Never request access to live case files. |

---

## Next Steps

1. **Contact Artifex** (`sales@artifex.com`) — get a commercial license quote for PyMuPDF <!-- pii-guard: allow (public vendor contact) -->
2. **Consult a business attorney** — entity formation, EULA drafting, liability structure
3. **Decide license enforcement model** — annual re-delivery is recommended (see Distribution Model above)
4. **Complete beta validation** — run 2–3 full cases end-to-end on your own matters
5. **Launch "Charter Firm" program** — offer 3–5 founding customers 50% off Year 1 in exchange for a testimonial, a brief case study, and a 30-minute feedback call. Creates urgency and a path to social proof.
6. **Bar association outreach** — post in your state bar's litigation section listserv. This reaches exactly your ICP at zero cost and with inherent credibility from a fellow practitioner.
7. **Write installation documentation** — step-by-step server setup guide for an IT-adjacent paralegal or office manager
