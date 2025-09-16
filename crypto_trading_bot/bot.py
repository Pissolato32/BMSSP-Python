import ccxt
import pandas as pd
import pandas_ta as ta
import os
import time
import logging
from dotenv import load_dotenv
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA
from web3 import Web3


# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to create exchange instance
def create_exchange(testnet=False, market_type='spot'):
    if testnet:
        config = {
            'apiKey': os.getenv('BINANCE_TESTNET_API_KEY'),
            'secret': os.getenv('BINANCE_TESTNET_SECRET_KEY'),
            'enableRateLimit': True,
            'options': {
                'defaultType': market_type,
                'adjustForTimeDifference': True,
            },
        }
        exchange = ccxt.binance(config)
        exchange.set_sandbox_mode(True)
        return exchange
    else:
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET_KEY'),
            'enableRateLimit': True,
            'options': {
                'defaultType': market_type,
                'adjustForTimeDifference': True,
            },
        }
        return ccxt.binance(config)

# Initialize exchange (set testnet=True for paper trading)
exchange = create_exchange(testnet=True)  # Change to True for testnet

print("Connected to Binance successfully!")

class SmaCross(Strategy):
    def init(self):
        self.sma10 = self.I(SMA, self.data.Close, 10)
        self.sma30 = self.I(SMA, self.data.Close, 30)

    def next(self):
        if crossover(self.sma10, self.sma30):
            self.buy(size=0.01)
        elif crossover(self.sma30, self.sma10):
            self.sell(size=0.01)

def fetch_data(symbol='BTC/USDT', timeframe='1h', limit=100):
    """Fetch OHLCV data from Binance and return as a Pandas DataFrame."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logging.error(f"Error fetching data: {e}")
        print(f"Error fetching data: {e}")
        return None

def add_indicators(df):
    """Add technical indicators to the DataFrame."""
    df.ta.sma(length=10, append=True, col_names=('SMA_10',))
    df.ta.sma(length=30, append=True, col_names=('SMA_30',))
    return df

def check_strategy(df):
    """Check the strategy and return a signal ('buy', 'sell', or 'hold')."""
    if len(df) < 2:
        return 'hold'
    last_row = df.iloc[-1]
    previous_row = df.iloc[-2]

    # Buy signal: short SMA crosses above long SMA
    if last_row['SMA_10'] > last_row['SMA_30'] and previous_row['SMA_10'] <= previous_row['SMA_30']:
        return 'buy'

    # Sell signal: short SMA crosses below long SMA
    if last_row['SMA_10'] < last_row['SMA_30'] and previous_row['SMA_10'] >= previous_row['SMA_30']:
        return 'sell'

    return 'hold'

def backtest_strategy(df, initial_balance=1000):
    """Simple backtest of the strategy on historical data."""
    balance = initial_balance
    position = 0  # 0: no position, 1: long
    trades = []
    entry_price = 0

    for i in range(30, len(df)):  # Start after SMA_30 is available
        current_df = df.iloc[:i+1]
        signal = check_strategy(current_df)

        if signal == 'buy' and position == 0:
            position = 1
            entry_price = current_df.iloc[-1]['Close']
            trades.append({'type': 'buy', 'price': entry_price, 'timestamp': current_df.index[-1]})
            logging.info(f"Backtest BUY at {entry_price}")
        elif signal == 'sell' and position == 1:
            exit_price = current_df.iloc[-1]['Close']
            if exit_price > entry_price:
                position = 0
                profit = (exit_price - entry_price) / entry_price * balance
                balance += profit
                trades.append({'type': 'sell', 'price': exit_price, 'timestamp': current_df.index[-1], 'profit': profit})
                logging.info(f"Backtest SELL at {exit_price}, Profit: {profit}")
                entry_price = 0

    final_balance = balance
    return final_balance, trades



def execute_trade(signal, symbol, amount):
    """Execute a buy or sell order."""
    try:
        if signal == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
            logging.info(f"Executed BUY order: {order}")
            print("BUY order executed:", order)
            return order
        elif signal == 'sell':
            order = exchange.create_market_sell_order(symbol, amount)
            logging.info(f"Executed SELL order: {order}")
            print("SELL order executed:", order)
            return order
    except Exception as e:
        logging.error(f"Error executing trade: {e}")
        print(f"Error executing trade: {e}")
        return None

# Main loop
in_position = False
entry_price = 0
symbol = 'BTC/USDT'
amount = 0.001  # Adjust based on your risk

# Example backtest
print("Running backtest...")
btc_data = fetch_data(symbol, '1h', 200)
if btc_data is not None:
    btc_data = add_indicators(btc_data)
    final_balance, trades = backtest_strategy(btc_data)
    print(f"Backtest final balance: {final_balance}")
    print(f"Number of trades: {len(trades)}")

    # Advanced backtest with backtesting.py
    print("Running advanced backtest...")
    bt = Backtest(btc_data, SmaCross, cash=10000, commission=.002)
    stats = bt.run()
    print(stats)
    # bt.plot()  # Uncomment to plot if in interactive environment

# Fetch BSC testnet balance
print("Fetching BSC testnet balance...")
w3 = Web3(Web3.HTTPProvider('https://data-seed-prebsc-1-s1.binance.org:8545/'))
address = Web3.to_checksum_address('0xcf64feb411538b16cf584010e37a97eac546d3ac')
if w3.is_connected():
    balance = w3.eth.get_balance(address)
    print(f"BSC Testnet BNB Balance: {w3.from_wei(balance, 'ether')} BNB")

    # Fetch USDT balance
    usdt_contract_address = '0x337610d27c682E347C9cD60BD4b3b107C9d34dDd'  # BSC testnet USDT
    erc20_abi = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        }
    ]
    contract = w3.eth.contract(address=usdt_contract_address, abi=erc20_abi)
    usdt_balance = contract.functions.balanceOf(address).call()
    print(f"BSC Testnet USDT Balance: {usdt_balance / 10**18} USDT")
else:
    print("Not connected to BSC testnet")

def get_balance():
    """Fetch and return the account balance."""
    try:
        balance = exchange.fetch_balance()
        return balance
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")
        print(f"Error fetching balance: {e}")
        return None

def get_valid_amount(signal, symbol, desired_amount):
    """Calculate a valid order amount based on balance and lot size."""
    try:
        balance = get_balance()
        if not balance:
            return desired_amount

        markets = exchange.load_markets()
        step_size = markets[symbol]['limits']['amount']['min']

        if signal == 'buy':
            usdt_free = balance.get('USDT', {}).get('free', 0)
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            max_amount = usdt_free / price
            valid_amount = (max_amount // step_size) * step_size
            return min(valid_amount, desired_amount)
        elif signal == 'sell':
            btc_free = balance.get('BTC', {}).get('free', 0)
            valid_amount = (btc_free // step_size) * step_size
            return min(valid_amount, desired_amount)
    except Exception as e:
        logging.error(f"Error calculating valid amount: {e}")
        return desired_amount

# Fetch Binance testnet balance
print("Fetching Binance testnet balance...")
balance = get_balance()
if balance:
    usdt_balance = balance.get('USDT', {}).get('free', 0)
    print(f"Binance Testnet USDT Balance: {usdt_balance} USDT")
    print(f"Full Balance: {balance}")

# Live/paper trading loop
while True:
    try:
        print("\nChecking for new candle...")
        df = fetch_data(symbol, '5m', 50)
        if df is not None:
            df = add_indicators(df)
            signal = check_strategy(df)
            print(f"Current signal: {signal}")
            print(f"Current position: {'In position' if in_position else 'Out of position'}")

            if signal == 'buy' and not in_position:
                valid_amount = get_valid_amount('buy', symbol, amount)
                if valid_amount > 0:
                    order = execute_trade('buy', symbol, valid_amount)
                    if order:
                        entry_price = order['average']
                        in_position = True
                else:
                    print("Insufficient balance or invalid amount to buy.")
            elif signal == 'sell' and in_position:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                if current_price > entry_price:
                    valid_amount = get_valid_amount('sell', symbol, amount)
                    if valid_amount > 0:
                        order = execute_trade('sell', symbol, valid_amount)
                        if order:
                            in_position = False
                            entry_price = 0
                    else:
                        print("Insufficient balance or invalid amount to sell.")
                else:
                    print(f"Current price {current_price} not above entry price {entry_price}, holding position.")

        time.sleep(300)  # Wait for next 5m candle
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
        print(f"Error in main loop: {e}")
        time.sleep(60)  # Wait 1 minute before retrying on error
