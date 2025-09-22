from json import load, JSONDecodeError
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_maker
from app.models.token import Token


async def add_logo_url_on_token(session: AsyncSession):
    # Read token metadata from app/db/data/token.json
    data_path = Path(__file__).resolve().parents[2] / "db" / "data" / "token.json"

    if not data_path.exists():
        print(f"token.json not found at {data_path}. Skipping.")
        return

    if data_path.stat().st_size == 0:
        print(f"token.json at {data_path} is empty. Nothing to process.")
        return

    try:
        with data_path.open("r", encoding="utf-8") as f:
            tokens = load(f)
    except JSONDecodeError as e:
        print(f"Failed to parse JSON from {data_path}: {e}. Skipping.")
        return
    except OSError as e:
        print(f"Failed to read {data_path}: {e}. Skipping.")
        return

    token_list = tokens.get("tokens")
    if not isinstance(token_list, list) or not token_list:
        print(f"No tokens found in {data_path} (missing or empty 'tokens' array).")
        return

    for token in token_list:
        address = token["address"]
        logo_url = token.get("logoURI", "")
        chain_id = token["chainId"]
        print(f"Updating token {address} on chain {chain_id} with logo_url {logo_url}")

        if logo_url:
            stmt = (
                Token.__table__.update()
                .where(Token.address == address)
                .where(Token.chain_id == chain_id)
                .values(logo_url=logo_url)
            )
            await session.execute(stmt)
    await session.commit()


async def _main():
    async with async_session_maker() as db_session:
        await add_logo_url_on_token(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
