from fastapi import Depends
from app.models.chain import Chain
from app.repositories.chain_repository import ChainRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.chain_repository import (
    get_chain_repository,
)


async def get_chain_by_id(
    chain_id: str,
    chain_repository: ChainRepository = Depends(get_chain_repository),
) -> Chain:
    chain = await chain_repository.find_by_or_raise(id=decode_id(chain_id))
    return chain
