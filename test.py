from datetime import time, date, timedelta, datetime

begin = time(hour=9)
step = 1

for _ in range(10):
    print('begin:', begin)
    begin = (datetime.combine(date.today(), begin) + timedelta(hours=step)).time()