Public-data inputs for personal fantasy-football analysis:

- nflverse player statistics and PFR-derived snap counts: https://github.com/nflverse/nflverse-data
- DynastyProcess player-ID crosswalk: https://github.com/dynastyprocess/data
- Sleeper public NFL player directory and current NFL season: https://docs.sleeper.com/

The directory is fetched at most once per 24 hours when a valid previous output exists. Injuries, player-news article bodies, league records, account credentials, and Odds API data are not published by this job. All player identities are retained, including retired and defensive players. NFL workload uses QB/RB/WR/TE and fullback offensive roles; those roles do not override Sleeper eligibility.

The source owners retain their applicable data terms. Preparation does not make the sources complete, official, instantaneous or independent of one another. Each publication records retrieval times, source file modification times when supplied, observed game coverage, unavailable components and unresolved identity mappings. Missing values remain null. Generated files are factual data for the private decision workflow, not an endorsement or fantasy recommendation.

The job runs on demand and approximately every six hours. GitHub schedules can be delayed or disabled after prolonged repository inactivity. Review the Actions page if data freshness fails. The Worker rejects stale manifests rather than reverting to expensive raw downloads.
