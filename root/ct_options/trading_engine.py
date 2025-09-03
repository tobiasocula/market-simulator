from fastapi import FastAPI, WebSocket, HTTPException
import pandas as pd
import logging
from contextlib import asynccontextmanager
import os
import asyncio
import traceback
from datetime import datetime, date, timedelta, time
from pydantic import BaseModel
from typing import Optional
import numpy as np
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import websockets

class AssetData(BaseModel):
    init_open_price: float
    init_vola: float

    # data for price stochastic modeling
    kappa: float # volatility mean reverting rate
    theta: float # volatility mean
    xi: float # volatility of volatility
    mu: float # asset yearly expected return
    rho: float # correlation volatility and asset price
    dt: float # timestep per iteration step (in years)

class OptionData(BaseModel):
    beta: float | int # decay parameter, for this model, this is constant for all contracts k,j
    gamma: float | int # parameter for the cross-excitation between contracts k and j, in the
    # formula for w_{k,j}
    mu: float | int # the static intensity per contract (also constant for all contracts here)
    contract_volume_mean: float | int # mean for lognormal sampling of option contract size
    contract_volume_std: float | int # std for lognormal sampling of option contract size
    expiry_times: list[int]
    strikes_per_expiry: int

class InitStruct(BaseModel):
    assetdata: AssetData
    optiondata: OptionData
    sleep_step: float

# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):

    # initialize app state
    app.state.num_traders_assets = None
    app.state.num_traders_options = None
    app.state.asset_price_drift = None
    app.state.asset_vola_drift = None

    app.state.streamed_time = None

    app.state.streamed_time_lock = asyncio.Lock()
    app.state.asset_price_lock = asyncio.Lock()
    app.state.asset_vola_lock = asyncio.Lock()

    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def asset_price_drift(params, sleep_step):
    async with app.state.asset_price_lock, app.state.asset_vola_lock:
        app.state.asset_price_drift = params.init_open_price
        app.state.asset_vola_drift = params.init_vola
    while True:
        # update price and vola using Heston model

        z1 = np.random.normal()
        z2 = np.random.normal()
        dw_s = np.sqrt(params.dt) * z1
        dw_v = np.sqrt(params.dt) * (params.rho * z1 + np.sqrt(1 - params.rho**2) * z2)

        # update volatility
        app.state.asset_vola_drift = app.state.asset_vola_drift + params.kappa * (params.theta - app.state.asset_vola_drift) * params.dt + params.xi * np.sqrt(app.state.asset_vola_drift) * dw_v
        
        # update price
        app.state.asset_price_drift = app.state.asset_price_drift * np.exp((params.mu - 0.5 * app.state.vola_drift**2) * params.dt + np.sqrt(app.state.asset_vola_drift) * dw_s)

        await asyncio.sleep(sleep_step)

async def asset_trading_cycle():
    pass

async def option_trading_cycle(params):
    pass



@app.post("/init")
async def init(data: InitStruct):
    
    asyncio.create_task(asset_price_drift(data.assetdata, data.sleep_step))

