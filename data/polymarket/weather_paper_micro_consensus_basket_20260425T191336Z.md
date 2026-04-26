# Weather consensus paper micro basket — 20260425T191336Z

Paper-only simulated strict-limit fills. No real order placed. Probabilities are crude station-normal proxy, stress-tested across bias/sigma.

Summary: filled 5 positions, requested $55, filled $50.3106, proxy EV $47.5503

## Paper ledger
| status | risk | market | side | limit | live ask/bid | fill $/shares/avg | p_side | EV | accounts |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| FILLED_LIMIT | robust | Seoul April 26 20C or higher | NO | 0.32 | 0.27/0.25 | $15.0/53.9136/0.2782 | 0.948 | 36.1275 | 17 |
| FILLED_LIMIT | robust | London April 26 18C | NO | 0.545 | 0.53/0.5 | $5.3106/10.02/0.53 | 0.770 | 2.4058 | 20 |
| FILLED_LIMIT | robust | Tokyo April 26 20C | NO | 0.575 | 0.56/0.53 | $10.0/17.8571/0.56 | 0.721 | 2.875 | 21 |
| FILLED_LIMIT | robust | Wellington April 26 17C | NO | 0.575 | 0.56/0.53 | $10.0/17.8571/0.56 | 0.724 | 2.9339 | 17 |
| FILLED_LIMIT | robust | Singapore April 26 33C | NO | 0.635 | 0.62/0.6 | $10.0/16.129/0.62 | 0.819 | 3.2081 | 17 |

## Rejected / watch after stress
| risk | market | side | edge | positive scenarios | worst | median |
|---|---|---|---:|---:|---:|---:|
| robust | Munich April 26 21C or higher | YES | 0.1955 | 17/20 | -0.0279 | 0.2355 |
| robust | Munich April 26 18C | NO | 0.1519 | 18/20 | -0.0303 | 0.1805 |
| robust | Seoul April 26 17C | YES | 0.2687 | 20/20 | 0.0325 | 0.1318 |
| robust | London April 26 20C | YES | 0.1665 | 18/20 | -0.0356 | 0.0982 |
| robust | Singapore April 26 31C | YES | 0.15 | 16/20 | -0.0858 | 0.0409 |