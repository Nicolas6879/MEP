# Cryptocurrency Arbitrage Agent

## Introduction
This is the first version (1.0.0) of the NEAR AI agent designed to identify and execute cryptocurrency arbitrage opportunities across multiple exchanges. Arbitrage is the practice of taking advantage of price differences between markets - buying a cryptocurrency on one exchange where it's cheaper and selling it on another where it's more expensive.

**Version**: 1.0.0 (Initial Release)

## Key Features
- Real-time scanning for arbitrage opportunities
- Support for multiple cryptocurrency trading pairs
- Detailed dashboards for analyzing price differences
- Simulated price data based on real market conditions
- Optional automatic trade execution
- Configurable profit thresholds and trading limits
- Price monitoring with historical data tracking

## Future Enhancements
In future versions, we plan to improve the flexibility of the agent by allowing users to configure key variables dynamically through chat inputs, eliminating the need for manual code modifications.

## Supported Exchanges
- Binance
- KuCoin
- Kraken
- OKX

## Supported Trading Pairs
- BTC-USDT
- ETH-USDT
- XRP-USDT
- NEAR-USDT
- SOL-USDT
- ADA-USDT
- DOT-USDT

## Setup Instructions

### Prerequisites
1. A CoinMarketCap API key (free tier available at [https://coinmarketcap.com/api/](https://coinmarketcap.com/api/))
2. (Optional) API keys for the exchanges you want to trade on

### Configuration
Before using the agent, you need to modify the following variables at the beginning of the code:

1. **COINMARKETCAP_API_KEY**: Your CoinMarketCap API key
2. **EXCHANGE_CREDENTIALS**: Your API keys and secrets for each exchange (only needed for auto-trading)
3. **DEFAULT_CONFIG**: Adjust trading parameters as needed
4. **TRADING_PAIRS**: Add or remove cryptocurrency pairs you want to monitor

Example:
```python
# CoinMarketCap API Key (get a free one at https://coinmarketcap.com/api/)
COINMARKETCAP_API_KEY = "your_api_key_here"  # Replace with your actual API key

# Exchange API credentials
EXCHANGE_CREDENTIALS = {
    "binance": {
        "api_key": "your_binance_api_key",
        "api_secret": "your_binance_api_secret"
    },
    # Other exchanges...
}
```

In future versions, these configurations will be adjustable dynamically through the chat interface, reducing the need for direct code modifications.

