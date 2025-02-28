from nearai.agents.environment import Environment
import requests
import time
import json
import os
import random
from datetime import datetime

#####################################################################
# USER CONFIGURATION SECTION - MODIFY THESE VALUES
#####################################################################

# CoinMarketCap API Key (get a free one at https://coinmarketcap.com/api/)
COINMARKETCAP_API_KEY = "a92f4e73-b6c0-41d4-9f56-672e21294828"  # Replace with your actual API key

# Exchange API credentials - Enter your own API keys and secrets here
# These are used for executing actual trades (when auto-trading is enabled)
EXCHANGE_CREDENTIALS = {
    "binance": {
        "api_key": "",  # Enter your Binance API key here
        "api_secret": ""  # Enter your Binance API secret here
    },
    "kucoin": {
        "api_key": "",  # Enter your KuCoin API key here
        "api_secret": ""  # Enter your KuCoin API secret here
    },
    "kraken": {
        "api_key": "",  # Enter your Kraken API key here
        "api_secret": ""  # Enter your Kraken API secret here
    },
    "okx": {
        "api_key": "",  # Enter your OKX API key here
        "api_secret": ""  # Enter your OKX API secret here
    }
}

# Default trading configuration - Adjust these values as needed
DEFAULT_CONFIG = {
    "min_profit": 1.0,       # Minimum profit percentage to consider an opportunity
    "trade_amount": 100,     # Amount in USDT per operation
    "max_daily_trades": 10,  # Maximum number of daily trades
    "auto_trading": False    # Automatic trading disabled by default
}

# Trading pairs to monitor - Add or remove pairs as needed
TRADING_PAIRS = [
    "BTC-USDT", "ETH-USDT", "XRP-USDT", "NEAR-USDT",
    "SOL-USDT", "ADA-USDT", "DOT-USDT"
]

#####################################################################
# SYSTEM CONFIGURATION - YOU CAN MODIFY THESE, BUT IT'S NOT REQUIRED
#####################################################################

# Exchange configuration for arbitrage simulation
# fee: Trading fee (%), withdrawal_fee: Withdrawal fee (%)
# price_variance: Price variation range compared to CoinMarketCap price (%)
EXCHANGES = {
    "binance": {
        "fee": 0.1,
        "withdrawal_fee": 0.05,
        "price_variance": (-0.1, 0.1)
    },
    "kucoin": {
        "fee": 0.1,
        "withdrawal_fee": 0.1,
        "price_variance": (-0.2, 0.3)
    },
    "kraken": {
        "fee": 0.16,
        "withdrawal_fee": 0.08,
        "price_variance": (-0.3, 0.2)
    },
    "okx": {
        "fee": 0.08,
        "withdrawal_fee": 0.07,
        "price_variance": (0.05, 0.35)
    }
}

# Symbol mapping for CoinMarketCap (some may have different names)
SYMBOL_MAPPING = {
    "BTC": "BTC",
    "ETH": "ETH", 
    "XRP": "XRP",
    "NEAR": "NEAR",
    "SOL": "SOL",
    "ADA": "ADA",
    "DOT": "DOT",
    "USDT": "USDT"
}

# Cache duration for price data (in seconds)
CACHE_DURATION = 60

#####################################################################
# SYSTEM VARIABLES - DO NOT MODIFY BELOW THIS LINE
#####################################################################

# For storing history of opportunities and operations
arbitrage_history = []
trades_history = []

# Current configuration (initialized with default values)
current_config = DEFAULT_CONFIG.copy()

# Price cache to avoid repeated API calls
price_cache = {}
price_cache_timestamp = 0

def get_token_prices():
    """Gets current token prices from CoinMarketCap"""
    global price_cache, price_cache_timestamp
    
    # If cache is recent, use it
    current_time = time.time()
    if current_time - price_cache_timestamp < CACHE_DURATION and price_cache:
        return price_cache
    
    # Extract unique symbols that we need to look up
    symbols_to_fetch = set()
    for pair in TRADING_PAIRS:
        base, quote = pair.split('-')
        symbols_to_fetch.add(base)
        symbols_to_fetch.add(quote)
    
    # Map symbols to CoinMarketCap IDs
    symbols_list = ",".join(SYMBOL_MAPPING.get(symbol, symbol) for symbol in symbols_to_fetch)
    
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        parameters = {
            "symbol": symbols_list,
            "convert": "USD"  # Use USD as base currency
        }
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY
        }
        
        response = requests.get(url, headers=headers, params=parameters, timeout=10)
        data = response.json()
        
        if "data" not in data:
            print(f"Error getting prices from CoinMarketCap: {data.get('status', {}).get('error_message', 'Unknown error')}")
            return price_cache  # Return old cache if there's an error
            
        # Update the cache
        prices = {}
        for symbol in symbols_to_fetch:
            mapped_symbol = SYMBOL_MAPPING.get(symbol, symbol)
            if mapped_symbol in data["data"]:
                prices[symbol] = float(data["data"][mapped_symbol]["quote"]["USD"]["price"])
        
        price_cache = prices
        price_cache_timestamp = current_time
        
        return prices
        
    except Exception as e:
        print(f"Error querying CoinMarketCap: {str(e)}")
        
        # If this is the first time and there's no cache, create sample data
        if not price_cache:
            # Reference prices (only as fallback if API fails)
            price_cache = {
                "BTC": 62000.0,
                "ETH": 3400.0,
                "XRP": 0.58,
                "NEAR": 1.78,
                "SOL": 145.0,
                "ADA": 0.45,
                "DOT": 7.40,
                "USDT": 1.0
            }
            price_cache_timestamp = current_time
            print("Using reference prices due to API error")
            
        return price_cache

def get_exchange_price(exchange, symbol, base_price):
    """Simulates the price in a specific exchange based on CoinMarketCap price"""
    min_var, max_var = EXCHANGES[exchange]["price_variance"]
    
    # Generate a variation within the configured range
    # We use a hash based on the exchange, symbol and current time (rounded to 5 minutes)
    # to maintain consistency during short periods of time
    seed = f"{exchange}{symbol}{time.time()//300}"
    hash_value = hash(seed) % 10000
    variation = min_var + (max_var - min_var) * (hash_value / 10000)
    
    # Apply variation to base price
    return base_price * (1 + variation / 100)

def find_arbitrage_opportunities(env):
    """Searches for arbitrage opportunities between exchanges using CoinMarketCap data"""
    opportunities = []
    
    # Get base prices from CoinMarketCap
    base_prices = get_token_prices()
    if not base_prices:
        return []
    
    for pair in TRADING_PAIRS:
        pair_prices = {}
        base, quote = pair.split('-')
        
        # If we don't have the price for either coin, skip
        if base not in base_prices or quote not in base_prices:
            print(f"Missing price for {base} or {quote}, skipping pair {pair}")
            continue
        
        # Calculate base price in USDT
        base_price_usd = base_prices[base]
        
        # Simulate prices on different exchanges
        for exchange_name, config in EXCHANGES.items():
            exchange_price = get_exchange_price(exchange_name, base, base_price_usd)
            pair_prices[exchange_name] = exchange_price
        
        # Identify the best exchange to buy and sell
        min_exchange = min(pair_prices, key=pair_prices.get)
        max_exchange = max(pair_prices, key=pair_prices.get)
        
        min_price = pair_prices[min_exchange]
        max_price = pair_prices[max_exchange]
        
        # Calculate percentage difference
        price_diff = ((max_price - min_price) / min_price) * 100
        
        # Estimate fees based on exchange configuration
        buy_fee_pct = EXCHANGES[min_exchange]["fee"]
        sell_fee_pct = EXCHANGES[max_exchange]["fee"]
        withdrawal_fee_pct = EXCHANGES[min_exchange]["withdrawal_fee"]
        
        buy_fee = min_price * (buy_fee_pct / 100)
        sell_fee = max_price * (sell_fee_pct / 100)
        withdrawal_fee = min_price * (withdrawal_fee_pct / 100)
        
        # Calculate profit after fees
        net_gain = max_price - min_price - buy_fee - sell_fee - withdrawal_fee
        net_gain_percent = (net_gain / min_price) * 100
        
        # Check if it meets the minimum profit configured and is positive
        if net_gain_percent > 0 and net_gain_percent >= current_config["min_profit"]:
            opportunity = {
                "pair": pair,
                "buy_exchange": min_exchange,
                "buy_price": min_price,
                "sell_exchange": max_exchange,
                "sell_price": max_price,
                "diff_percent": price_diff,
                "net_gain_percent": net_gain_percent,
                "timestamp": datetime.now().isoformat()
            }
            opportunities.append(opportunity)
            arbitrage_history.append(opportunity)
            
            # If auto-trading is enabled, execute the trade
            if current_config["auto_trading"] and len(trades_history) < current_config["max_daily_trades"]:
                execute_trade(opportunity, env)
    
    return opportunities

def execute_trade(opportunity, env):
    """Executes an arbitrage trade (simulated)"""
    # In a real implementation, this would call the trading APIs
    trade = {
        "pair": opportunity["pair"],
        "buy_exchange": opportunity["buy_exchange"],
        "buy_price": opportunity["buy_price"],
        "sell_exchange": opportunity["sell_exchange"],
        "sell_price": opportunity["sell_price"],
        "amount": current_config["trade_amount"],
        "profit": opportunity["net_gain_percent"],
        "profit_amount": (current_config["trade_amount"] * opportunity["net_gain_percent"]) / 100,
        "timestamp": datetime.now().isoformat(),
        "status": "completed"  # In a real implementation, could be "pending", "completed", "failed"
    }
    
    trades_history.append(trade)
    
    # Notify the user
    notification = f"🔄 Trade executed automatically:\n"
    notification += f"Buy: {trade['amount']/trade['buy_price']:.6f} {opportunity['pair'].split('-')[0]} "
    notification += f"on {trade['buy_exchange'].upper()} at ${trade['buy_price']:.4f}\n"
    notification += f"Sell: {trade['amount']/trade['buy_price']:.6f} {opportunity['pair'].split('-')[0]} "
    notification += f"on {trade['sell_exchange'].upper()} at ${trade['sell_price']:.4f}\n"
    notification += f"Estimated profit: ${trade['profit_amount']:.2f} ({trade['profit']:.2f}%)"
    
    env.add_reply(notification)
    
    return trade

def format_opportunities(opportunities):
    """Formats opportunities to display to the user"""
    if not opportunities:
        return "No significant arbitrage opportunities found at this time."
    
    result = "🚀 Arbitrage opportunities detected:\n\n"
    
    for i, op in enumerate(opportunities, 1):
        result += f"#{i} - Pair: {op['pair']}\n"
        result += f"   Buy on: {op['buy_exchange'].upper()} at ${op['buy_price']:.4f}\n"
        result += f"   Sell on: {op['sell_exchange'].upper()} at ${op['sell_price']:.4f}\n"
        result += f"   Potential profit: {op['diff_percent']:.2f}%\n\n"
    
    result += "Note: This information does not constitute financial advice. "
    result += "Consider trading fees, withdrawal fees and risks before executing any trade."
    
    return result

def get_agent_status():
    """Gets the current status of the agent"""
    status = "📊 Current Status of Arbitrage Agent:\n\n"
    
    # Configuration
    status += "Configuration:\n"
    status += f"- Minimum profit percentage: {current_config['min_profit']}%\n"
    status += f"- Amount per trade: {current_config['trade_amount']} USDT\n"
    status += f"- Maximum daily trades: {current_config['max_daily_trades']}\n"
    status += f"- Auto-trading: {'ENABLED' if current_config['auto_trading'] else 'DISABLED'}\n\n"
    
    # Configured exchanges
    status += "Configured exchanges:\n"
    for exchange in EXCHANGES:
        has_credentials = bool(EXCHANGE_CREDENTIALS[exchange]["api_key"])
        status += f"- {exchange}: {'✓' if has_credentials else '✗'}\n"
    
    # Price information
    cache_time = "Not available" if price_cache_timestamp == 0 else datetime.fromtimestamp(price_cache_timestamp).strftime('%H:%M:%S')
    status += f"\nLast price update: {cache_time}\n"
    status += f"Trades today: {len(trades_history)}/{current_config['max_daily_trades']}\n"
    
    # If API key is configured
    status += f"\nCoinMarketCap API: {'✓ Configured' if COINMARKETCAP_API_KEY != 'YOUR_API_KEY_HERE' else '✗ Not configured'}\n"
    
    return status

def format_trades_history():
    """Formats the history of executed trades"""
    if not trades_history:
        return "No trade history available."
    
    result = "📝 Trade History:\n\n"
    
    for i, trade in enumerate(trades_history, 1):
        result += f"#{i} - {trade['timestamp'][:19]} - {trade['pair']}\n"
        result += f"   Buy: {trade['buy_exchange'].upper()} at ${trade['buy_price']:.4f}\n"
        result += f"   Sell: {trade['sell_exchange'].upper()} at ${trade['sell_price']:.4f}\n"
        result += f"   Amount: ${trade['amount']} USDT\n"
        result += f"   Profit: ${trade['profit_amount']:.2f} ({trade['profit']:.2f}%)\n"
        result += f"   Status: {trade['status']}\n\n"
    
    return result

def setup_coinmarketcap_api(api_key):
    """Configures the CoinMarketCap API key"""
    global COINMARKETCAP_API_KEY
    
    if api_key and api_key != "YOUR_API_KEY_HERE":
        COINMARKETCAP_API_KEY = api_key
        # Force cache update to test the new API key
        global price_cache_timestamp
        price_cache_timestamp = 0
        
        # Try to get prices to verify the API key works
        try:
            prices = get_token_prices()
            if prices:
                return f"✅ CoinMarketCap API Key configured successfully. Data retrieved successfully."
            else:
                return f"⚠️ API Key configured, but couldn't get data. Verify the key and API access."
        except Exception as e:
            return f"❌ Error configuring API Key: {str(e)}"
    else:
        return f"❌ Invalid API Key. Please provide a valid API key."

def show_dashboard_all(env):
    """Shows a dashboard with all pairs and their arbitrage opportunities"""
    result = "📊 COMPLETE ARBITRAGE DASHBOARD\n\n"
    
    # Get current opportunities
    opportunities = []
    
    # Get base prices from CoinMarketCap
    base_prices = get_token_prices()
    if not base_prices:
        return "Couldn't get current prices. Try again later."
    
    for pair in TRADING_PAIRS:
        base, quote = pair.split('-')
        
        if base not in base_prices:
            continue
            
        base_price = base_prices[base]
        
        # Get prices on each exchange
        exchange_data = []
        for exchange_name, config in EXCHANGES.items():
            price = get_exchange_price(exchange_name, base, base_price)
            
            # Calculate fees
            buy_fee_pct = config["fee"]
            withdrawal_fee_pct = config["withdrawal_fee"]
            cost_after_fees = price * (1 + buy_fee_pct/100) + price * (withdrawal_fee_pct/100)
            effective_sell_value = price * (1 - buy_fee_pct/100)
            
            exchange_data.append({
                "exchange": exchange_name,
                "price": price,
                "cost_after_fees": cost_after_fees,
                "effective_sell_value": effective_sell_value
            })
        
        # Calculate the best arbitrage opportunity
        if len(exchange_data) >= 2:
            best_sell = max(exchange_data, key=lambda x: x["effective_sell_value"])
            best_buy = min(exchange_data, key=lambda x: x["cost_after_fees"])
            
            # Only if they are different exchanges
            if best_sell["exchange"] != best_buy["exchange"]:
                net_profit = best_sell["effective_sell_value"] - best_buy["cost_after_fees"]
                net_profit_pct = (net_profit / best_buy["price"]) * 100
                
                # Only add if profit is positive
                if net_profit_pct > 0:
                    opportunities.append({
                        "pair": pair,
                        "buy_exchange": best_buy["exchange"],
                        "buy_price": best_buy["price"],
                        "sell_exchange": best_sell["exchange"],
                        "sell_price": best_sell["price"],
                        "net_profit_pct": net_profit_pct
                    })
    
    # Sort opportunities by potential profit
    opportunities.sort(key=lambda x: x["net_profit_pct"], reverse=True)
    
    # Show opportunities table
    if opportunities:
        result += "💰 ARBITRAGE OPPORTUNITIES\n"
        result += "┌─────────┬─────────────┬────────────┬─────────────┬────────────┬──────────┐\n"
        result += "│   PAIR  │   BUY ON    │   PRICE    │   SELL ON   │   PRICE    │  PROFIT  │\n"
        result += "├─────────┼─────────────┼────────────┼─────────────┼────────────┼──────────┤\n"
        
        for op in opportunities:
            pair = op["pair"]
            buy_ex = op["buy_exchange"].upper()
            buy_price = f"${op['buy_price']:.4f}"
            sell_ex = op["sell_exchange"].upper()
            sell_price = f"${op['sell_price']:.4f}"
            profit = f"{op['net_profit_pct']:.2f}%"
            
            result += f"│ {pair.ljust(7)} │ {buy_ex.ljust(11)} │ {buy_price.ljust(10)} │ {sell_ex.ljust(11)} │ {sell_price.ljust(10)} │ {profit.ljust(8)} │\n"
        
        result += "└─────────┴─────────────┴────────────┴─────────────┴────────────┴──────────┘\n\n"
    else:
        result += "No positive arbitrage opportunities found at this time.\n\n"
    
    # Add summary of average prices
    result += "📈 AVERAGE PRICES BY CRYPTOCURRENCY\n"
    for pair in TRADING_PAIRS:
        base, quote = pair.split('-')
        if base in base_prices:
            result += f"{base}: ${base_prices[base]:.4f}\n"
    
    cache_time = "Not available" if price_cache_timestamp == 0 else datetime.fromtimestamp(price_cache_timestamp).strftime('%H:%M:%S')
    result += f"\nℹ️ Data updated: {cache_time}\n"
    result += "To see details for a specific pair, use the command 'dashboard [PAIR]'.\n"
    
    return result

def show_dashboard(pair, env):
    """
    Generates a visual dashboard for a specific pair,
    showing ordered prices and other relevant data
    """
    # Check if the pair is valid
    if pair not in TRADING_PAIRS:
        similar_pairs = [p for p in TRADING_PAIRS if pair.split('-')[0] in p]
        if similar_pairs:
            return f"Pair not recognized. Perhaps you meant one of these? {', '.join(similar_pairs)}"
        else:
            return f"Pair not recognized. Available pairs: {', '.join(TRADING_PAIRS)}"
    
    # Get current prices
    base_prices = get_token_prices()
    if not base_prices:
        return "Couldn't get current prices. Try again later."
    
    base, quote = pair.split('-')
    
    # Check if we have the price for this pair
    if base not in base_prices:
        return f"Couldn't get price for {base}."
    
    base_price = base_prices[base]
    
    # Get prices on each exchange
    exchange_data = []
    for exchange_name, config in EXCHANGES.items():
        price = get_exchange_price(exchange_name, base, base_price)
        
        # Calculate additional data
        buy_fee_pct = config["fee"]
        withdrawal_fee_pct = config["withdrawal_fee"]
        
        # Calculate total cost including fees to buy 1 unit
        cost_after_fees = price * (1 + buy_fee_pct/100) + price * (withdrawal_fee_pct/100)
        
        # Calculate effective value (price after subtracting selling fees)
        effective_sell_value = price * (1 - buy_fee_pct/100)
        
        # Add to list
        exchange_data.append({
            "exchange": exchange_name,
            "price": price,
            "trading_fee": buy_fee_pct,
            "withdrawal_fee": withdrawal_fee_pct,
            "cost_after_fees": cost_after_fees,
            "effective_sell_value": effective_sell_value
        })
    
    # Sort exchanges by price (high to low)
    exchange_data.sort(key=lambda x: x["price"], reverse=True)
    
    # Calculate the best arbitrage opportunity
    if len(exchange_data) >= 2:
        # For buying, we need the exchange with lowest total cost after fees
        best_buy = min(exchange_data, key=lambda x: x["cost_after_fees"])
        
        # For selling, we need the exchange with highest effective value after selling fees
        best_sell = max(exchange_data, key=lambda x: x["effective_sell_value"])
        
        # Only if they are different exchanges
        if best_sell["exchange"] != best_buy["exchange"]:
            price_diff = ((best_sell["price"] - best_buy["price"]) / best_buy["price"]) * 100
            net_profit = best_sell["effective_sell_value"] - best_buy["cost_after_fees"]
            net_profit_pct = (net_profit / best_buy["price"]) * 100
        else:
            price_diff = 0
            net_profit_pct = 0
    else:
        price_diff = 0
        net_profit_pct = 0
        best_buy = None
        best_sell = None
    
    # Generate dashboard in text format
    dashboard = f"📊 DASHBOARD: {pair} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n\n"
    
    # Reference price
    dashboard += f"📈 Reference price ({base}): ${base_price:.4f}\n\n"
    
    # Ordered price table
    dashboard += "🏆 EXCHANGE RANKING BY PRICE (HIGH TO LOW)\n"
    dashboard += "┌─────────────┬────────────┬────────────┬────────────┬────────────┐\n"
    dashboard += "│   EXCHANGE  │    PRICE   │    FEE %   │ WITH FEES  │  EFF. SELL │\n"
    dashboard += "├─────────────┼────────────┼────────────┼────────────┼────────────┤\n"
    
    for data in exchange_data:
        exchange_name = data["exchange"].upper()
        price = f"${data['price']:.4f}"
        fees = f"{data['trading_fee']}%"
        cost = f"${data['cost_after_fees']:.4f}"
        eff_value = f"${data['effective_sell_value']:.4f}"
        
        dashboard += f"│ {exchange_name.ljust(11)} │ {price.ljust(10)} │ {fees.ljust(10)} │ {cost.ljust(10)} │ {eff_value.ljust(10)} │\n"
    
    dashboard += "└─────────────┴────────────┴────────────┴────────────┴────────────┘\n\n"
    
    # Arbitrage opportunity
    dashboard += "💰 BEST ARBITRAGE OPPORTUNITY\n"
    if len(exchange_data) >= 2 and best_buy and best_sell and best_buy["exchange"] != best_sell["exchange"]:
        dashboard += f"Buy on: {best_buy['exchange'].upper()} at ${best_buy['price']:.4f}\n"
        dashboard += f"Sell on: {best_sell['exchange'].upper()} at ${best_sell['price']:.4f}\n"
        dashboard += f"Price difference: {price_diff:.2f}%\n"
        
        if net_profit_pct > 0:
            dashboard += f"Net profit (after fees): {net_profit_pct:.2f}%\n\n"
        else:
            dashboard += f"Net profit (after fees): {net_profit_pct:.2f}% ❌ Not profitable\n\n"
    else:
        dashboard += "No profitable arbitrage opportunity between different exchanges.\n\n"
    
    # Price variations
    max_var = max(exchange_data, key=lambda x: x["price"])["price"]
    min_var = min(exchange_data, key=lambda x: x["price"])["price"]
    avg_var = sum(data["price"] for data in exchange_data) / len(exchange_data)
    spread = ((max_var - min_var) / avg_var) * 100
    
    dashboard += "📉 VARIATION STATISTICS\n"
    dashboard += f"Maximum price: ${max_var:.4f}\n"
    dashboard += f"Minimum price: ${min_var:.4f}\n"
    dashboard += f"Average price: ${avg_var:.4f}\n"
    dashboard += f"Spread between exchanges: {spread:.2f}%\n\n"
    
    # Note about data updates
    cache_time = "Not available" if price_cache_timestamp == 0 else datetime.fromtimestamp(price_cache_timestamp).strftime('%H:%M:%S')
    dashboard += f"ℹ️ Data updated: {cache_time}\n"
    dashboard += "To update prices, use the 'scan' command.\n"
    dashboard += "To see arbitrage opportunities, use the 'dashboard_all' command.\n"
    
    return dashboard

def handle_command(cmd, env):
    """Handles specific user commands"""
    global COINMARKETCAP_API_KEY
    
    # Main commands
    cmd_lower = cmd.lower()
    
    # Scan command
    if cmd_lower == "scan":
        opportunities = find_arbitrage_opportunities(env)
        return format_opportunities(opportunities)
    
    # History command
    elif cmd_lower == "history":
        if not arbitrage_history:
            return "No arbitrage opportunity history recorded."
        
        result = "📊 Arbitrage opportunity history:\n\n"
        for i, op in enumerate(arbitrage_history[-10:], 1):  # Show last 10
            result += f"#{i} - {op['timestamp'][:19]} - {op['pair']}: "
            result += f"{op['diff_percent']:.2f}% ({op['buy_exchange']} → {op['sell_exchange']})\n"
        
        return result
    
    # Trades command
    elif cmd_lower == "trades":
        return format_trades_history()
    
    # Status command
    elif cmd_lower == "status":
        return get_agent_status()
    
    # Dashboards
    elif cmd_lower.startswith("dashboard "):
        parts = cmd.split()
        if len(parts) < 2:
            return "Correct format: dashboard [PAIR]"
        
        pair = parts[1].upper()
        return show_dashboard(pair, env)
    
    # Complete dashboard
    elif cmd_lower == "dashboard_all":
        return show_dashboard_all(env)
    
    # Help command
    elif cmd_lower == "help":
        help_message = """📚 Available commands:

scan - Search for current arbitrage opportunities
history - View history of detected opportunities
trades - View history of executed trades
status - View current agent status
dashboard [PAIR] - Show detailed dashboard for a specific pair (e.g., dashboard BTC-USDT)
dashboard_all - Show dashboard with all pairs and opportunities
config [param] [value] - Configure trading parameters
setup_api [api_key] - Configure CoinMarketCap API key
help - Show this help

Usage examples:
dashboard BTC-USDT - Shows detailed analysis for Bitcoin
config min_profit 1.5 - Sets the minimum profit to 1.5%
config auto_trading true - Enables auto-trading
setup_api YOUR_API_KEY - Configures the CoinMarketCap API key
"""
        return help_message
    
    # Command to configure CoinMarketCap API key
    elif cmd_lower.startswith("setup_api "):
        parts = cmd.split()
        if len(parts) < 2:
            return "Correct format: setup_api [api_key]"
        
        api_key = parts[1]
        return setup_coinmarketcap_api(api_key)
    
    # Configuration command
    elif cmd_lower.startswith("config "):
        parts = cmd.split()
        if len(parts) < 3:
            return "Correct format: config [param] [value]"
        
        param = parts[1].lower()
        value = parts[2].lower()
        
        if param == "min_profit":
            try:
                current_config["min_profit"] = float(value)
                return f"Minimum profit percentage set to {value}%"
            except:
                return "Value must be a number."
        
        elif param == "trade_amount":
            try:
                current_config["trade_amount"] = float(value)
                return f"Amount per trade set to {value} USDT"
            except:
                return "Value must be a number."
        
        elif param == "max_daily_trades":
            try:
                current_config["max_daily_trades"] = int(value)
                return f"Maximum daily trades set to {value}"
            except:
                return "Value must be an integer."
        
        elif param == "auto_trading":
            if value in ["true", "1", "yes", "on"]:
                current_config["auto_trading"] = True
                return "Auto-trading ENABLED"
            elif value in ["false", "0", "no", "off"]:
                current_config["auto_trading"] = False
                return "Auto-trading DISABLED"
            else:
                return "Invalid value. Use 'true' or 'false'."
        
        else:
            return f"Parameter '{param}' not recognized."
    
    # Monitoring command
    elif cmd_lower.startswith("monitor "):
        parts = cmd.split()
        if len(parts) != 3:
            return "Correct format: monitor [PAIR] [TIME_IN_SECONDS]"
        
        pair = parts[1].upper()
        try:
            duration = int(parts[2])
        except:
            return "Time must be a number in seconds."
        
        if duration > 300:  # Limit to 5 minutes
            return "Please use a maximum time of 300 seconds (5 minutes)."
        
        # Check if the pair is valid
        if pair not in TRADING_PAIRS:
            similar_pairs = [p for p in TRADING_PAIRS if pair.split('-')[0] in p]
            if similar_pairs:
                return f"Pair not recognized. Perhaps you meant one of these? {', '.join(similar_pairs)}"
            else:
                return f"Pair not recognized. Available pairs: {', '.join(TRADING_PAIRS)}"
        
        result = f"📈 Monitoring {pair} for {duration} seconds...\n\n"
        
        # Perform monitoring
        start_time = time.time()
        end_time = start_time + duration
        check_interval = 10  # Check every 10 seconds (to not overload the API)
        next_check = start_time
        
        price_history = {}
        base, quote = pair.split('-')
        
        while time.time() < end_time:
            if time.time() >= next_check:
                # Get base prices
                base_prices = get_token_prices()
                if base in base_prices:
                    base_price = base_prices[base]
                    
                    # Simulate prices on different exchanges
                    for exchange_name in EXCHANGES:
                        price = get_exchange_price(exchange_name, base, base_price)
                        if exchange_name not in price_history:
                            price_history[exchange_name] = []
                        price_history[exchange_name].append(price)
                
                next_check = time.time() + check_interval
                
                # Wait a small interval to not completely block
                time.sleep(1)
        
        # Analyze monitoring results
        report = f"✅ Monitoring completed for {pair}:\n\n"
        
        for exchange, prices in price_history.items():
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                avg_price = sum(prices) / len(prices)
                volatility = ((max_price - min_price) / avg_price) * 100 if avg_price > 0 else 0
                
                report += f"{exchange.upper()}:\n"
                report += f"  Minimum price: ${min_price:.4f}\n"
                report += f"  Maximum price: ${max_price:.4f}\n"
                report += f"  Average price: ${avg_price:.4f}\n"
                report += f"  Volatility: {volatility:.2f}%\n\n"
        
        report += "Use 'scan' to see current arbitrage opportunities."
        
        return report
    
    # If not a known command, indicate it
    else:
        return None

def run(env: Environment):
    # Basic system
    system_message = """You are an advanced cryptocurrency arbitrage agent that helps identify buying and selling 
    opportunities across different exchanges. You can scan the market in real-time 
    to find significant price differences and execute trades automatically.
    
    Available commands:
    - 'scan': Search for current arbitrage opportunities
    - 'history': Show history of detected opportunities
    - 'trades': Show history of executed trades
    - 'status': Show current agent status
    - 'dashboard [PAIR]': Show detailed dashboard for a pair
    - 'dashboard_all': Show dashboard with all pairs
    - 'config [param] [value]': Configure trading parameters
    - 'setup_api [api_key]': Configure CoinMarketCap API key
    - 'help': Show detailed help
    
    Always remember to inform the user about risks and important considerations."""
    
    prompt = {"role": "system", "content": system_message}
    
    # Process messages
    user_messages = env.list_messages()
    
    if user_messages:
        last_message = user_messages[-1]["content"]
        
        # Check if it's a command
        command_response = handle_command(last_message, env)
        
        if command_response:
            # If it was a command, use the command response
            env.add_reply(command_response)
        else:
            # If it wasn't a command, use the model to respond
            result = env.completion([prompt] + user_messages)
            env.add_reply(result)
    else:
        # Welcome message
        welcome_message = """Welcome to the advanced cryptocurrency arbitrage agent. Here you can find buying and selling opportunities across different exchanges and execute trades automatically.

Remember that cryptocurrency trading involves significant risks, including loss of capital. It's important that you understand the risks and important considerations before you start trading.

To get started, I recommend you review the available commands:

* 'scan': Search for current arbitrage opportunities
* 'history': Show history of detected opportunities
* 'trades': Show history of executed trades
* 'status': Show current agent status
* 'dashboard [PAIR]': Show detailed dashboard for a pair
* 'dashboard_all': Show dashboard with all pairs
* 'config [param] [value]': Configure trading parameters
* 'setup_api [api_key]': Configure CoinMarketCap API key
* 'help': Show detailed help

⚠️ Important: To use this agent with real-time data, you need to configure a CoinMarketCap API key with the setup_api command

Which command would you like to execute?"""
        env.add_reply(welcome_message)
    
    # Request next input
    env.request_user_input()

run(env)
