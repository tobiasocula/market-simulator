import requests
from typing import Optional, Literal, ClassVar
from pydantic import BaseModel, Field
import httpx
from datetime import time
import numpy as np
import pandas as pd
import asyncio
from ..continuous_trading.classes import ContinuousMarket, baseurl


async def main():
    async with httpx.AsyncClient() as client:
        market = ContinuousMarket(
            open_time=time(hour=9),
            close_time=time(hour=17),
            participants=[]
        )
        r = await client.post(baseurl + "/init_market", json=market.to_serializable_dict())
        if r.status_code == 200:
            print(r.json())
        else:
            print(f"Status code: {r.status_code}, content: {r.text}")  # no await here


asyncio.run(main())