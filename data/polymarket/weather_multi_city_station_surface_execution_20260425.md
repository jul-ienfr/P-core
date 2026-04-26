# Multi-city station/source execution queue

station direct Weather.com/Wunderground + Polymarket CLOB books; probabilities are crude normal proxy, not calibrated

## Best queue
- **paper_micro_strict_limit** Seoul April 26 NO 20°C higher: station RKSI max=18C prob=0.858 ask=0.28 fill20=0.2934 edge=0.578 accts=10 blockers=none
- **paper_micro_strict_limit** Munich April 26 YES 21°C higher: station EDDM max=20C prob=0.3605 ask=0.029 fill20=0.0346 edge=0.3315 accts=11 blockers=none
- **paper_micro_strict_limit** Seoul April 26 YES 18°C exact: station RKSI max=18C prob=0.279 ask=0.067 fill20=0.0825 edge=0.212 accts=10 blockers=none
- **paper_micro_strict_limit** Seoul April 26 YES 17°C exact: station RKSI max=18C prob=0.2185 ask=0.011 fill20=0.0269 edge=0.2075 accts=10 blockers=none
- **paper_micro_strict_limit** Seoul April 27 YES 15°C exact: station RKSI max=16C prob=0.2185 ask=0.029 fill20=0.0514 edge=0.1895 accts=6 blockers=none
- **paper_micro_strict_limit** Munich April 26 NO 18°C exact: station EDDM max=20C prob=0.8951 ask=0.71 fill20=0.71 edge=0.1851 accts=11 blockers=none
- **paper_micro_strict_limit** London April 26 NO 18°C exact: station EGLC max=18C prob=0.721 ask=0.54 fill20=0.555 edge=0.181 accts=11 blockers=none
- **paper_micro_strict_limit** Shanghai April 26 YES 21°C exact: station ZSPD max=22C prob=0.2185 ask=0.047 fill20=0.0713 edge=0.1715 accts=10 blockers=none
- **paper_micro_strict_limit** Beijing April 26 NO 25°C exact: station ZBAA max=26C prob=0.7815 ask=0.61 fill20=0.61 edge=0.1715 accts=8 blockers=none
- **paper_micro_strict_limit** Seoul April 27 NO 19°C exact: station RKSI max=16C prob=0.9691 ask=0.82 fill20=0.82 edge=0.1491 accts=6 blockers=none
- **paper_micro_strict_limit** Shanghai April 26 NO 23°C exact: station ZSPD max=22C prob=0.7815 ask=0.64 fill20=0.64 edge=0.1415 accts=10 blockers=none
- **paper_micro_strict_limit** Ankara April 26 YES 22°C exact: station LTAC max=21C prob=0.2185 ask=0.079 fill20=0.0799 edge=0.1395 accts=9 blockers=none
- **paper_micro_strict_limit** Seoul April 27 YES 16°C exact: station RKSI max=16C prob=0.279 ask=0.14 fill20=0.1699 edge=0.139 accts=6 blockers=none
- **paper_micro_strict_limit** Munich April 26 NO 19°C exact: station EDDM max=20C prob=0.7815 ask=0.65 fill20=0.6508 edge=0.1315 accts=11 blockers=none
- **paper_micro_strict_limit** Beijing April 26 YES 27°C exact: station ZBAA max=26C prob=0.2185 ask=0.09 fill20=0.1058 edge=0.1285 accts=8 blockers=none
- **paper_micro_strict_limit** Shanghai April 27 YES 25°C exact: station ZSPD max=26C prob=0.2185 ask=0.09 fill20=0.1506 edge=0.1285 accts=3 blockers=none
- **paper_micro_strict_limit** Ankara April 26 YES 23°C higher: station LTAC max=21C prob=0.142 ask=0.019 fill20=0.0356 edge=0.123 accts=9 blockers=none
- **paper_micro_strict_limit** Ankara April 26 NO 20°C exact: station LTAC max=21C prob=0.7815 ask=0.7 fill20=0.7068 edge=0.0815 accts=9 blockers=none
- **paper_micro_strict_limit** Beijing April 26 NO 24°C exact: station ZBAA max=26C prob=0.8951 ask=0.82 fill20=0.82 edge=0.0751 accts=8 blockers=none
- **watch_source_book** Seoul April 27 NO 18°C exact: station RKSI max=16C prob=0.8951 ask=0.78 fill20=0.78 edge=0.1151 accts=6 blockers=none
- **watch_source_book** Shanghai April 27 NO 27°C exact: station ZSPD max=26C prob=0.7815 ask=0.68 fill20=0.6931 edge=0.1015 accts=3 blockers=none
- **watch_source_book** Shanghai April 26 YES 20°C exact: station ZSPD max=22C prob=0.1049 ask=0.01 fill20=0.0439 edge=0.0949 accts=10 blockers=none
- **watch_source_book** Seoul April 26 YES 16°C exact: station RKSI max=18C prob=0.1049 ask=0.01 fill20=0.0152 edge=0.0949 accts=10 blockers=none
- **watch_source_book** Seoul April 27 NO 20°C exact: station RKSI max=16C prob=0.9944 ask=0.9 fill20=0.9 edge=0.0944 accts=6 blockers=none
- **watch_source_book** Seoul April 27 YES 14°C exact: station RKSI max=16C prob=0.1049 ask=0.016 fill20=0.031 edge=0.0889 accts=6 blockers=none

## Station checks
- Shanghai April 26: station=ZSPD maxC=22 status=200 markets=11 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Shanghai Pudong International Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Shanghai Pudong International Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Munich April 26: station=EDDM maxC=20 status=200 markets=11 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Munich Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Munich Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/de/munich/EDDM.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Beijing April 26: station=ZBAA maxC=26 status=200 markets=143 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Beijing Capital International Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Beijing Capital International Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/cn/beijing/ZBAA.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- London April 26: station=EGLC maxC=18 status=200 markets=11 src=This market will resolve to the temperature range that contains the highest temperature recorded at the London City Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the London City Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/gb/london/EGLC.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Seoul April 27: station=RKSI maxC=16 status=200 markets=110 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Incheon Intl Airport Station in degrees Celsius on 27 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Incheon Intl Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/kr/incheon/RKSI.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Ankara April 26: station=LTAC maxC=21 status=200 markets=143 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Esenboğa Intl Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Esenboğa Intl Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/tr/%C3%A7ubuk/LTAC.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Shanghai April 27: station=ZSPD maxC=26 status=200 markets=110 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Shanghai Pudong International Airport Station in degrees Celsius on 27 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Shanghai Pudong International Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.
- Seoul April 26: station=RKSI maxC=18 status=200 markets=143 src=This market will resolve to the temperature range that contains the highest temperature recorded at the Incheon Intl Airport Station in degrees Celsius on 26 Apr '26.

The resolution source for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Incheon Intl Airport Station once information is finalized, available here: https://www.wunderground.com/history/daily/kr/incheon/RKSI.

To toggle between Fahrenheit and Celsius, click the gear icon next to the search bar and switch the Temperature setting between °F and °C.

This market can not resolve to "Yes" until all data for this date has been finalized.

The resolution source for this market measures temperatures to whole degrees Celsius (eg, 9°C). Thus, this is the level of precision that will be used when resolving the market.

Any revisions to temperatures recorded after data is finalized for this market's timeframe will not be considered for this market's resolution.