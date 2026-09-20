Public-data inputs for personal fantasy-football analysis:

- nflverse player statistics and PFR-derived snap counts: https://github.com/nflverse/nflverse-data
- DynastyProcess player-ID crosswalk: https://github.com/dynastyprocess/data
- Sleeper public NFL player directory and current NFL season: https://docs.sleeper.com/

The directory is fetched at most once per 24 hours when a compatible previous output exists. Upgrading an older snapshot without external-ID indexes requires one initial refresh. Injuries, player-news article bodies, league records, account credentials, and Odds API data are not published by this job. All player identities are retained, including retired and defensive players. NFL workload uses QB/RB/WR/TE plus FB/HB roles normalized to RB; those roles do not override Sleeper eligibility.

The ID crosswalk is not filtered by position, because position designations can lag a role change. Missing Sleeper IDs can be filled through unique shared GSIS, RotoWire, ESPN or Sportradar identifiers present in both public sources. The job records this mapping basis. Ambiguous links, already-claimed IDs and name-only similarities do not produce an automatic join. Missing PFR links remain unresolved.

The source owners retain their applicable data terms. Preparation does not make the sources complete, official, instantaneous or independent of one another. Each publication records retrieval times, source file modification times when supplied, observed game coverage, unavailable components and unresolved identity mappings. Missing values remain null. Generated files are factual data for the private decision workflow, not an endorsement or fantasy recommendation.

The job runs on demand and approximately every six hours. GitHub schedules can be delayed or disabled after prolonged repository inactivity. Review the Actions page if data freshness fails. The Worker rejects stale manifests rather than reverting to expensive raw downloads.

## v1.3.2 request-cost reduction

Weekly workload objects additionally embed a compact identity lookup for their player IDs and names. Each match is copied from the full global crosswalk, including duplicates or ambiguous matches outside the selected week. Missing keys still use the complete identity shards. This index changes retrieval cost, not player coverage, identity rules, source freshness or missing-data semantics. It is backward compatible with schema 1 readers. No paid data source is introduced.
