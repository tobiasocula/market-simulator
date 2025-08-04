import httpx
from typing import Optional, Literal, ClassVar
from pydantic import BaseModel, Field, PrivateAttr
from datetime import time
import numpy as np
import pandas as pd

baseurl = "http://localhost:8000"

class MarketParticipant(BaseModel):

    maxid: ClassVar[int] = 0

    init_balance: int | float
    # exclude = true: means that this won't be expected in the initialization
    balance: Optional[float] = Field(default=None, exclude=True)
    id: Optional[int] = Field(default=None, exclude=True)

    def model_post_init(self, __context):
        if self.balance is None:
            object.__setattr__(self, 'balance', self.init_balance)

        MarketParticipant.maxid = MarketParticipant.maxid + 1
        self.id = MarketParticipant.maxid

    def update_balance(self, newb: float | int):
        assert self.balance is not None, AssertionError()
        self.balance += newb

    async def make_order(self,
                         volume: int,
                         buy: bool,
                         curtime: time,
                         price: Optional[float] = None):
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(baseurl + "/place_order", json=Order(
                    participant_id=self.id,
                    side="buy" if buy else "sell",
                    volume=volume,
                    price=price,
                    time=curtime
                ).to_json())
                if resp.status_code == 200:
                    print(resp.content)
                else:
                    print(f"Unexpected status code: {resp.status_code}, content: {await resp}")
        except Exception as e:
            print('Error during request:', e)

        

class Order(BaseModel):

    allids: ClassVar[list[int]] = []

    participant_id: int
    side: Literal["buy", "sell"]
    price: Optional[float] = None # None = market order
    volume: int
    time: time
    id: Optional[int] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not Order.allids:
            self.id = 0
        else:
            self.id = max(Order.allids) + 1
        Order.allids.append(self.id)

    def to_json(self):
        return {
            "participant_id": self.participant_id,
            "side": self.side,
            "price": self.price,
            "volume": self.volume,
            "time": self.time.isoformat(),
            "id": self.id
        }

class ContinuousMarket(BaseModel):

    model_config = {
        "arbitrary_types_allowed": True,
    }

    open_time: time
    close_time: time
    participants: list[MarketParticipant] = []
    _order_book: pd.DataFrame = PrivateAttr()
    state: Optional[int] = Field(default=None, exclude=True)
    current_price: Optional[float] = Field(default=1, exclude=True)

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize order_book internally here if it's None:
        object.__setattr__(self, '_order_book', pd.DataFrame(
            columns=['Time', 'Buy', 'Price', 'Volume', 'PartID']
        ))

    def add_participant(self, p: MarketParticipant):
        self.participants.append(p)

    def to_serializable_dict(self):
        return {
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "participants": [p.model_dump() for p in self.participants]
        }
    
    def random_participants(self, amount=None):
        if amount is None:
            amount = np.random.randint(0, len(self.participants))
        arr = np.random.randint(0, len(self.participants), amount)
        return [self.participants[a] for a in arr]
    
    def order_book_json(self):
        return self._order_book.to_dict()
    
    async def initialize(self):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(baseurl + "/init_market", json=self.to_serializable_dict())
            if resp.status_code == 200:
                result = resp.json()
                if result.get('ok'):
                    print("Market initialized successfully")
                    return  # success
                else:
                    raise RuntimeError(f"Market init endpoint responded with failure: {result.get('message')}")
            else:
                raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")

        
            



