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
# from web3 import Web3 # Unused import removed


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
    print(f"Fetching {timeframe} data for {symbol}...")
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        print("Data fetched successfully.")
        return df
    except ccxt.NetworkError as e:
        logging.error(f"Error fetching data (network error): {e}")
        print(f"Error fetching data (network error): {e}")
        return None
    except ccxt.ExchangeError as e:
        logging.error(f"Error fetching data (exchange error): {e}")
        print(f"Error fetching data (exchange error): {e}")
        return None
    except Exception as e:
        logging.error(f"Error fetching data (unexpected error): {e}")
        print(f"Error fetching data (unexpected error): {e}")
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
    print(f"Attempting to execute {signal} order for {amount} of {symbol}...")
    try:
        if signal == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
            logging.info(f"Executed BUY order: {order}")
            print("BUY order executed successfully:", order)
            return order
        elif signal == 'sell':
            order = exchange.create_market_sell_order(symbol, amount)
            logging.info(f"Executed SELL order: {order}")
            print("SELL order executed successfully:", order)
            return order
    except ccxt.InsufficientFunds as e:
        logging.error(f"Error executing trade: {e}")
        print(f"Error executing trade: Insufficient funds. {e}")
        return None
    except ccxt.NetworkError as e:
        logging.error(f"Error executing trade (network error): {e}")
        print(f"Error executing trade (network error): {e}")
        return None
    except ccxt.ExchangeError as e:
        logging.error(f"Error executing trade (exchange error): {e}")
        print(f"Error executing trade (exchange error): {e}")
        return None
    except Exception as e:
        logging.error(f"Error executing trade (unexpected error): {e}")
        print(f"Error executing trade (unexpected error): {e}")
        return None

# Main loop
in_position = False
entry_price = 0
symbol = 'BTC/USDT'
amount = 0.001  # Adjust based on your risk

# # Example backtest (Temporarily commented out to focus on live trading)
# print("Running backtest...")
# btc_data = fetch_data(symbol, '1h', 200)
# if btc_data is not None:
#     btc_data = add_indicators(btc_data)
#     final_balance, trades = backtest_strategy(btc_data)
#     print(f"Backtest final balance: {final_balance}")
#     print(f"Number of trades: {len(trades)}")
# 
#     # Advanced backtest with backtesting.py (Temporarily commented out)
#     print("Running advanced backtest...")
#     bt = Backtest(btc_data, SmaCross, cash=10000, commission=.002)
#     stats = bt.run()
#     print(stats)
#     # bt.plot()  # Uncomment to plot if in interactive environment



def get_balance():
    """Fetch and return the account balance."""
    print("Fetching account balance...")
    try:
        balance = exchange.fetch_balance()
        if balance:
            usdt_free = balance.get('USDT', {}).get('free', 0)
            btc_free = balance.get('BTC', {}).get('free', 0)
            print(f"Available Balance -> USDT: {usdt_free}, BTC: {btc_free}")
        return balance
    except ccxt.NetworkError as e:
        logging.error(f"Error fetching balance (network error): {e}")
        print(f"Error fetching balance (network error): {e}")
        return None
    except ccxt.ExchangeError as e:
        logging.error(f"Error fetching balance (exchange error): {e}")
        print(f"Error fetching balance (exchange error): {e}")
        return None
    except Exception as e:
        logging.error(f"Error fetching balance (unexpected error): {e}")
        print(f"Error fetching balance (unexpected error): {e}")
        return None

def get_valid_amount(signal, symbol, desired_amount):
    """Calculate a valid order amount based on balance and lot size."""
    print(f"Calculating valid amount for {signal} order...")
    try:
        balance = get_balance()
        if not balance:
            print("Could not fetch balance, using desired amount.")
            return desired_amount

        markets = exchange.load_markets()
        step_size = markets[symbol]['limits']['amount']['min']
        print(f"Market step size for {symbol} is {step_size}.")

        if signal == 'buy':
            usdt_free = balance.get('USDT', {}).get('free', 0)
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            print(f"Current price of {symbol} is {price} USDT.")
            if price <= 0:
                print("Invalid price, cannot calculate amount.")
                return 0
            max_amount = usdt_free / price
            valid_amount = (max_amount // step_size) * step_size
            final_amount = min(valid_amount, desired_amount)
            print(f"Calculated valid amount to buy: {final_amount}")
            return final_amount
        elif signal == 'sell':
            btc_free = balance.get('BTC', {}).get('free', 0)
            valid_amount = (btc_free // step_size) * step_size
            final_amount = min(valid_amount, desired_amount)
            print(f"Calculated valid amount to sell: {final_amount}")
            return final_amount
    except ccxt.NetworkError as e:
        logging.error(f"Error calculating valid amount (network error): {e}")
        print(f"Error calculating valid amount (network error): {e}")
        return 0
    except ccxt.ExchangeError as e:
        logging.error(f"Error calculating valid amount (exchange error): {e}")
        print(f"Error calculating valid amount (exchange error): {e}")
        return 0
    except Exception as e:
        logging.error(f"Error calculating valid amount (unexpected error): {e}")
        print(f"Error calculating valid amount (unexpected error): {e}")
        return 0

# Fetch Binance testnet balance
print("--- Initial Setup ---")
balance = get_balance()
if balance:
    usdt_balance = balance.get('USDT', {}).get('free', 0)
    print(f"Initial Binance Testnet USDT Balance: {usdt_balance} USDT")
    # print(f"Full Balance: {balance}") # This can be very verbose
print("--- Starting Live Trading Loop ---")


# Live/paper trading loop
while True:
    try:
        print("\nChecking for new candle...")
        df = fetch_data(symbol, '5m', 50)
        if df is not None and not df.empty:
            df = add_indicators(df)
            signal = check_strategy(df)
            print(f"Current signal: {signal}")
            print(f"Current position: {'In position' if in_position else 'Out of position'}")

            if signal == 'buy' and not in_position:
                valid_amount = get_valid_amount('buy', symbol, amount)
                if valid_amount > 0:
                    order = execute_trade('buy', symbol, valid_amount)
                    if order and 'average' in order and order['average']:
                        entry_price = order['average']
                        in_position = True
                    else:
                        print("Order execution failed or did not return average price.")
                else:
                    print("Insufficient balance or invalid amount to buy. Holding.")
            elif signal == 'sell' and in_position:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                print(f"Current Price: {current_price}, Entry Price: {entry_price}")
                if current_price > entry_price:
                    valid_amount = get_valid_amount('sell', symbol, amount)
                    if valid_amount > 0:
                        order = execute_trade('sell', symbol, valid_amount)
                        if order:
                            in_position = False
                            entry_price = 0
                    else:
                        print("Insufficient balance or invalid amount to sell. Holding.")
                else:
                    print(f"Current price {current_price} is not above entry price {entry_price}, holding position.")
        else:
            print("Could not fetch data, will retry.")

        print(f"Waiting for 5 minutes before next check...")
        time.sleep(300)  # Wait for next 5m candle
    except ccxt.NetworkError as e:
        logging.error(f"Error in main loop (network error): {e}")
        print(f"Error in main loop (network error): {e}")
        time.sleep(60)
    except ccxt.ExchangeError as e:
        logging.error(f"Error in main loop (exchange error): {e}")
        print(f"Error in main loop (exchange error): {e}")
        time.sleep(60)
    except Exception as e:
        logging.error(f"An unexpected error occurred in main loop: {e}")
        print(f"An unexpected error occurred in main loop: {e}")
        time.sleep(60)  # Wait 1 minute before retrying on error