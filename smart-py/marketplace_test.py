"""Unit tests for the Marketplace class.

"""

import os
import smartpy as sp

# Import the FA2, minter and marketplaces modules
fa2Contract = sp.io.import_script_from_url(f"file://{os.getcwd()}/fa2.py")
minterContract = sp.io.import_script_from_url(f"file://{os.getcwd()}/objkt_swap_v1.py")
marketplaceContract = sp.io.import_script_from_url(f"file://{os.getcwd()}/marketplace.py")


class RecipientContract(sp.Contract):
    """This contract simulates a user that can recive tez transfers.

    It should only be used to test that tez transfers are sent correctly.

    """

    def __init__(self):
        """Initializes the contract.

        """
        self.init()

    @sp.entry_point
    def default(self, unit):
        """Default entrypoint that allows receiving tez transfers in the same
        way as one would do with a normal tz wallet.

        """
        # Define the input parameter data type
        sp.set_type(unit, sp.TUnit)

        # Do nothing, just receive tez
        pass


def get_test_environment():
    # Create the test accounts
    admin = sp.test_account("admin")
    artist1 = sp.test_account("artist1")
    artist2 = sp.test_account("artist2")
    collector1 = sp.test_account("collector1")
    collector2 = sp.test_account("collector2")

    # Initialize the OBJKT contract
    objkt = fa2Contract.FA2(
        config=fa2Contract.FA2_config(),
        admin=admin.address,
        meta=sp.utils.metadata_of_url("ipfs://aaa"))

    # Initialize the hDAO contract
    hdao = fa2Contract.FA2(
        config=fa2Contract.FA2_config(),
        admin=admin.address,
        meta=sp.utils.metadata_of_url("ipfs://bbb"))

    # Initialize the new OBJKT contract
    newobjkt = fa2Contract.FA2(
        config=fa2Contract.FA2_config(),
        admin=admin.address,
        meta=sp.utils.metadata_of_url("ipfs://ccc"))

    # Initialize a dummy curate contract
    curate = sp.Contract()

    # Initialize the minter (v1) contract
    minter = minterContract.OBJKTSwap(
        objkt=objkt.address,
        hdao=hdao.address,
        manager=admin.address,
        metadata=sp.utils.metadata_of_url("ipfs://ddd"),
        curate=curate.address)

    # Initialize the marketplace contract
    marketplace = marketplaceContract.Marketplace(
        manager=admin.address,
        metadata=sp.utils.metadata_of_url("ipfs://eee"),
        allowed_fa2s=sp.big_map({objkt.address: sp.unit}),
        fee=25)

    # Initialize the recipient contracts
    fee_recipient = RecipientContract()
    royalties_recipient = RecipientContract()

    # Add all the contracts to the test scenario
    scenario = sp.test_scenario()
    scenario += objkt
    scenario += hdao
    scenario += newobjkt
    scenario += curate
    scenario += minter
    scenario += marketplace
    scenario += fee_recipient
    scenario += royalties_recipient

    # Change the OBJKT token administrator to the minter contract
    scenario += objkt.set_administrator(minter.address).run(sender=admin)

    # Change the marketplace fee recipient
    scenario += marketplace.update_fee_recipient(fee_recipient.address).run(
        sender=admin)

    # Save all the variables in a test environment dictionary
    testEnvironment = {
        "scenario" : scenario,
        "admin" : admin,
        "artist1" : artist1,
        "artist2" : artist2,
        "collector1" : collector1,
        "collector2" : collector2,
        "objkt" : objkt,
        "hdao" : hdao,
        "newobjkt" : newobjkt,
        "curate" : curate,
        "minter" : minter,
        "marketplace" : marketplace,
        "fee_recipient": fee_recipient,
        "royalties_recipient": royalties_recipient}

    return testEnvironment


@sp.add_test(name="Test swap and collect")
def test_swap_and_collect():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    collector2 = testEnvironment["collector2"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]
    fee_recipient = testEnvironment["fee_recipient"]
    royalties_recipient = testEnvironment["royalties_recipient"]

    # Mint an OBJKT
    editions = 100
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Check that there are no swaps before
    scenario.verify(~marketplace.data.swaps.contains(0))
    scenario.verify(~marketplace.has_swap(0))
    scenario.verify(marketplace.data.counter == 0)
    scenario.verify(marketplace.get_swaps_counter() == 0)

    # Check that tez transfers are not allowed when swapping
    swapped_editions = 50
    edition_price = 1000000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=royalties_recipient.address).run(valid=False, sender=artist1, amount=sp.tez(3))

    # Swap the OBJKT in the marketplace contract
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=royalties_recipient.address).run(sender=artist1)

    # Check that the OBJKT ledger information is correct
    scenario.verify(objkt.data.ledger[(artist1.address, objkt_id)].balance == editions - swapped_editions)
    scenario.verify(objkt.data.ledger[(marketplace.address, objkt_id)].balance == swapped_editions)

    # Check that the swaps big map is correct
    scenario.verify(marketplace.data.swaps.contains(0))
    scenario.verify(marketplace.data.swaps[0].issuer == artist1.address)
    scenario.verify(marketplace.data.swaps[0].fa2 == objkt.address)
    scenario.verify(marketplace.data.swaps[0].objkt_id == objkt_id)
    scenario.verify(marketplace.data.swaps[0].objkt_amount == swapped_editions)
    scenario.verify(marketplace.data.swaps[0].xtz_per_objkt == sp.mutez(edition_price))
    scenario.verify(marketplace.data.swaps[0].royalties == royalties)
    scenario.verify(marketplace.data.swaps[0].creator == royalties_recipient.address)
    scenario.verify(marketplace.data.counter == 1)

    # Check that the on-chain views work
    scenario.verify(marketplace.has_swap(0))
    scenario.verify(marketplace.get_swap(0).issuer == artist1.address)
    scenario.verify(marketplace.get_swap(0).fa2 == objkt.address)
    scenario.verify(marketplace.get_swap(0).objkt_id == objkt_id)
    scenario.verify(marketplace.get_swap(0).objkt_amount == swapped_editions)
    scenario.verify(marketplace.get_swap(0).xtz_per_objkt == sp.mutez(edition_price))
    scenario.verify(marketplace.get_swap(0).royalties == royalties)
    scenario.verify(marketplace.get_swap(0).creator == royalties_recipient.address)
    scenario.verify(marketplace.get_swaps_counter() == 1)

    # Check that collecting fails if the collector is the swap issuer
    scenario += marketplace.collect(0).run(valid=False, sender=artist1, amount=sp.mutez(edition_price))

    # Check that collecting fails if the exact tez amount is not provided
    scenario += marketplace.collect(0).run(valid=False, sender=collector1, amount=sp.mutez(edition_price - 1))
    scenario += marketplace.collect(0).run(valid=False, sender=collector1, amount=sp.mutez(edition_price + 1))

    # Collect the OBJKT with two different collectors
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))
    scenario += marketplace.collect(0).run(sender=collector2, amount=sp.mutez(edition_price))

    # Check that all the tez have been sent and the swaps big map has been updated
    scenario.verify(marketplace.balance == sp.mutez(0))
    scenario.verify(fee_recipient.balance == sp.utils.nat_to_mutez(int(edition_price * (25 / 1000) * 2)))
    scenario.verify(royalties_recipient.balance == sp.utils.nat_to_mutez(int(edition_price * (royalties / 1000) * 2)))
    scenario.verify(marketplace.data.swaps[0].objkt_amount == swapped_editions - 2)
    scenario.verify(marketplace.get_swap(0).objkt_amount == swapped_editions - 2)

    # Check that the OBJKT ledger information is correct
    scenario.verify(objkt.data.ledger[(artist1.address, objkt_id)].balance == editions - swapped_editions)
    scenario.verify(objkt.data.ledger[(marketplace.address, objkt_id)].balance == swapped_editions - 2)
    scenario.verify(objkt.data.ledger[(collector1.address, objkt_id)].balance == 1)
    scenario.verify(objkt.data.ledger[(collector2.address, objkt_id)].balance == 1)

    # Check that only the swapper can cancel the swap
    scenario += marketplace.cancel_swap(0).run(valid=False, sender=collector1)
    scenario += marketplace.cancel_swap(0).run(valid=False, sender=artist1, amount=sp.tez(3))
    scenario += marketplace.cancel_swap(0).run(sender=artist1)

    # Check that the OBJKT ledger information is correct
    scenario.verify(objkt.data.ledger[(artist1.address, objkt_id)].balance == editions - 2)
    scenario.verify(objkt.data.ledger[(marketplace.address, objkt_id)].balance == 0)
    scenario.verify(objkt.data.ledger[(collector1.address, objkt_id)].balance == 1)
    scenario.verify(objkt.data.ledger[(collector2.address, objkt_id)].balance == 1)

    # Check that the swaps big map has been updated
    scenario.verify(~marketplace.data.swaps.contains(0))
    scenario.verify(~marketplace.has_swap(0))
    scenario.verify(marketplace.get_swaps_counter() == 1)

    # Check that the swap cannot be cancelled twice
    scenario += marketplace.cancel_swap(0).run(valid=False, sender=artist1)


@sp.add_test(name="Test free collect")
def test_free_collect():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]
    fee_recipient = testEnvironment["fee_recipient"]
    royalties_recipient = testEnvironment["royalties_recipient"]

    # Mint an OBJKT
    editions = 100
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Swap the OBJKT in the marketplace contract for a price of 0 tez
    swapped_editions = 50
    edition_price = 0
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=royalties_recipient.address).run(sender=artist1)

    # Collect the OBJKT
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Check that all the tez have been sent and the swaps big map has been updated
    scenario.verify(marketplace.balance == sp.mutez(0))
    scenario.verify(fee_recipient.balance == sp.mutez(0))
    scenario.verify(royalties_recipient.balance == sp.mutez(0))
    scenario.verify(marketplace.data.swaps[0].objkt_amount == swapped_editions - 1)

    # Check that the OBJKT ledger information is correct
    scenario.verify(objkt.data.ledger[(artist1.address, objkt_id)].balance == editions - swapped_editions)
    scenario.verify(objkt.data.ledger[(marketplace.address, objkt_id)].balance == swapped_editions - 1)
    scenario.verify(objkt.data.ledger[(collector1.address, objkt_id)].balance == 1)


@sp.add_test(name="Test very cheap collect")
def test_very_cheap_collect():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]
    fee_recipient = testEnvironment["fee_recipient"]
    royalties_recipient = testEnvironment["royalties_recipient"]

    # Mint an OBJKT
    editions = 100
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Swap the OBJKT in the marketplace contract for a very cheap price
    swapped_editions = 50
    edition_price = 2
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=royalties_recipient.address).run(sender=artist1)

    # Collect the OBJKT
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Check that all the tez have been sent and the swaps big map has been updated
    scenario.verify(marketplace.balance == sp.mutez(0))
    scenario.verify(fee_recipient.balance == sp.utils.nat_to_mutez(int(edition_price * (25 / 1000) * 2)))
    scenario.verify(royalties_recipient.balance == sp.utils.nat_to_mutez(int(edition_price * (royalties / 1000) * 2)))
    scenario.verify(marketplace.data.swaps[0].objkt_amount == swapped_editions - 1)

    # Check that the OBJKT ledger information is correct
    scenario.verify(objkt.data.ledger[(artist1.address, objkt_id)].balance == editions - swapped_editions)
    scenario.verify(objkt.data.ledger[(marketplace.address, objkt_id)].balance == swapped_editions - 1)
    scenario.verify(objkt.data.ledger[(collector1.address, objkt_id)].balance == 1)


@sp.add_test(name="Test update fee")
def test_update_fee():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    marketplace = testEnvironment["marketplace"]

    # Check the original fee
    scenario.verify(marketplace.data.fee == 25)
    scenario.verify(marketplace.get_fee() == 25)

    # Check that only the admin can update the fees
    new_fee = 100
    scenario += marketplace.update_fee(new_fee).run(valid=False, sender=artist1)
    scenario += marketplace.update_fee(new_fee).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.update_fee(new_fee).run(sender=admin)

    # Check that the fee is updated
    scenario.verify(marketplace.data.fee == new_fee)
    scenario.verify(marketplace.get_fee() == new_fee)

    # Check that if fails if we try to set a fee that its too high
    new_fee = 500
    scenario += marketplace.update_fee(new_fee).run(valid=False, sender=admin)


@sp.add_test(name="Test update fee recipient")
def test_update_fee_recipient():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    artist2 = testEnvironment["artist2"]
    marketplace = testEnvironment["marketplace"]
    fee_recipient = testEnvironment["fee_recipient"]

    # Check the original fee recipient
    scenario.verify(marketplace.data.fee_recipient == fee_recipient.address)
    scenario.verify(marketplace.get_fee_recipient() == fee_recipient.address)

    # Check that only the admin can update the fee recipient
    new_fee_recipient = artist1.address
    scenario += marketplace.update_fee_recipient(new_fee_recipient).run(valid=False, sender=artist1)
    scenario += marketplace.update_fee_recipient(new_fee_recipient).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.update_fee_recipient(new_fee_recipient).run(sender=admin)

    # Check that the fee recipient is updated
    scenario.verify(marketplace.data.fee_recipient == new_fee_recipient)
    scenario.verify(marketplace.get_fee_recipient() == new_fee_recipient)

    # Check that the fee recipient cannot update the fee recipient
    new_fee_recipient = artist2.address
    scenario += marketplace.update_fee_recipient(new_fee_recipient).run(valid=False, sender=artist1)


@sp.add_test(name="Test transfer and accept manager")
def test_transfer_and_accept_manager():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    artist2 = testEnvironment["artist2"]
    marketplace = testEnvironment["marketplace"]

    # Check the original manager
    scenario.verify(marketplace.data.manager == admin.address)
    scenario.verify(marketplace.get_manager() == admin.address)

    # Check that only the admin can transfer the manager
    new_manager = artist1.address
    scenario += marketplace.transfer_manager(new_manager).run(valid=False, sender=artist1)
    scenario += marketplace.transfer_manager(new_manager).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.transfer_manager(new_manager).run(sender=admin)

    # Check that the proposed manager is updated
    scenario.verify(marketplace.data.proposed_manager.open_some() == new_manager)

    # Check that only the proposed manager can accept the manager position
    scenario += marketplace.accept_manager().run(valid=False, sender=admin)
    scenario += marketplace.accept_manager().run(valid=False, sender=artist1, amount=sp.tez(3))
    scenario += marketplace.accept_manager().run(sender=artist1)

    # Check that the manager is updated
    scenario.verify(marketplace.data.manager == new_manager)
    scenario.verify(marketplace.get_manager() == new_manager)
    scenario.verify(~marketplace.data.proposed_manager.is_some())

    # Check that only the new manager can propose a new manager
    new_manager = artist2.address
    scenario += marketplace.transfer_manager(new_manager).run(valid=False, sender=admin)
    scenario += marketplace.transfer_manager(new_manager).run(sender=artist1)

    # Check that the proposed manager is updated
    scenario.verify(marketplace.data.proposed_manager.open_some() == new_manager)


@sp.add_test(name="Test update metadata")
def test_update_metadata():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    marketplace = testEnvironment["marketplace"]

    # Check that only the admin can update the metadata
    new_metadata = sp.record(key="", value=sp.pack("ipfs://zzzz"))
    scenario += marketplace.update_metadata(new_metadata).run(valid=False, sender=artist1)
    scenario += marketplace.update_metadata(new_metadata).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.update_metadata(new_metadata).run(sender=admin)

    # Check that the metadata is updated
    scenario.verify(marketplace.data.metadata[new_metadata.key] == new_metadata.value)

    # Add some extra metadata
    extra_metadata = sp.record(key="aaa", value=sp.pack("ipfs://ffff"))
    scenario += marketplace.update_metadata(extra_metadata).run(sender=admin)

    # Check that the two metadata entries are present
    scenario.verify(marketplace.data.metadata[new_metadata.key] == new_metadata.value)
    scenario.verify(marketplace.data.metadata[extra_metadata.key] == extra_metadata.value)


@sp.add_test(name="Test add and remove fa2")
def test_add_and_remove_fa2():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    newobjkt = testEnvironment["newobjkt"]
    marketplace = testEnvironment["marketplace"]

    # Mint a newOBJKT
    objkt_id = 0
    editions = 100
    newobjkt.mint(
        address=artist1.address,
        amount=editions,
        token_id=objkt_id,
        token_info={"" : sp.utils.bytes_of_string("ipfs://ccc")}).run(sender=admin)

    # Add the marketplace contract as an operator to be able to swap it
    scenario += newobjkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Check that it is not possible to swap the token
    swapped_editions = 50
    edition_price = 1000000
    royalties = 100
    scenario += marketplace.swap(
        fa2=newobjkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Check the view mode
    scenario.verify(marketplace.is_allowed_fa2(objkt.address))
    scenario.verify(~marketplace.is_allowed_fa2(newobjkt.address))

    # Check that only the admin can update the allowed FA2 contracts list
    new_fa2 = newobjkt.address
    scenario += marketplace.add_fa2(new_fa2).run(valid=False, sender=artist1)
    scenario += marketplace.add_fa2(new_fa2).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.add_fa2(new_fa2).run(sender=admin)

    # Check that the new FA2 token is now part of the allowed FA2 contracts
    scenario.verify(marketplace.data.allowed_fa2s.contains(objkt.address))
    scenario.verify(marketplace.data.allowed_fa2s.contains(new_fa2))
    scenario.verify(marketplace.is_allowed_fa2(objkt.address))
    scenario.verify(marketplace.is_allowed_fa2(new_fa2))

    # Check that now is possible to swap the newOBJKT
    scenario += marketplace.swap(
        fa2=newobjkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Check that the newOBJKT ledger information is correct
    scenario.verify(newobjkt.data.ledger[(artist1.address, objkt_id)].balance == editions - swapped_editions)
    scenario.verify(newobjkt.data.ledger[(marketplace.address, objkt_id)].balance == swapped_editions)

    # Check that the swaps big map is correct
    scenario.verify(marketplace.data.swaps.contains(0))
    scenario.verify(marketplace.data.swaps[0].issuer == artist1.address)
    scenario.verify(marketplace.data.swaps[0].fa2 == newobjkt.address)
    scenario.verify(marketplace.data.swaps[0].objkt_id == objkt_id)
    scenario.verify(marketplace.data.swaps[0].objkt_amount == swapped_editions)
    scenario.verify(marketplace.data.swaps[0].xtz_per_objkt == sp.mutez(edition_price))
    scenario.verify(marketplace.data.swaps[0].royalties == royalties)
    scenario.verify(marketplace.data.swaps[0].creator == artist1.address)

    # Remove the newOBJKT token from the allowed fa2 list
    scenario += marketplace.remove_fa2(newobjkt.address).run(valid=False, sender=artist1)
    scenario += marketplace.remove_fa2(newobjkt.address).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.remove_fa2(newobjkt.address).run(sender=admin)

    # Check that now is not allowed to trade newOBJKT tokens
    scenario.verify(marketplace.data.allowed_fa2s.contains(objkt.address))
    scenario.verify(~marketplace.data.allowed_fa2s.contains(newobjkt.address))
    scenario.verify(marketplace.is_allowed_fa2(objkt.address))
    scenario.verify(~marketplace.is_allowed_fa2(newobjkt.address))
    scenario += marketplace.swap(
        fa2=newobjkt.address,
        objkt_id=objkt_id,
        objkt_amount=1,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Check that however it is still possible to collect the previous swap and to cancel it
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))
    scenario += marketplace.cancel_swap(0).run(sender=artist1)

    # Check that the newOBJKT ledger information is correct
    scenario.verify(newobjkt.data.ledger[(artist1.address, objkt_id)].balance == editions - 1)
    scenario.verify(newobjkt.data.ledger[(marketplace.address, objkt_id)].balance == 0)
    scenario.verify(newobjkt.data.ledger[(collector1.address, objkt_id)].balance == 1)


@sp.add_test(name="Test set pause swaps")
def test_set_pause_swaps():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]

    # Mint an OBJKT
    editions = 100
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Swap one OBJKT in the marketplace contract
    swapped_editions = 10
    edition_price = 1000000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Collect the OBJKT
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Pause the swaps and make sure only the admin can do it
    scenario += marketplace.set_pause_swaps(True).run(valid=False, sender=collector1)
    scenario += marketplace.set_pause_swaps(True).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.set_pause_swaps(True).run(sender=admin)

    # Check that only the swaps are paused
    scenario.verify(marketplace.data.swaps_paused)
    scenario.verify(~marketplace.data.collects_paused)

    # Check that swapping is not allowed
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Check that collecting is still allowed
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Check that cancel swaps are still allowed
    scenario += marketplace.cancel_swap(0).run(sender=artist1)

    # Unpause the swaps again
    scenario += marketplace.set_pause_swaps(False).run(sender=admin)

    # Check that swapping and collecting is possible again
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)
    scenario += marketplace.collect(1).run(sender=collector1, amount=sp.mutez(edition_price))
    scenario += marketplace.cancel_swap(1).run(sender=artist1)


@sp.add_test(name="Test set pause collects")
def test_set_pause_collects():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]

    # Mint an OBJKT
    editions = 100
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Swap one OBJKT in the marketplace contract
    swapped_editions = 10
    edition_price = 1000000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Collect the OBJKT
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Pause the collects and make sure only the admin can do it
    scenario += marketplace.set_pause_collects(True).run(valid=False, sender=collector1)
    scenario += marketplace.set_pause_collects(True).run(valid=False, sender=admin, amount=sp.tez(3))
    scenario += marketplace.set_pause_collects(True).run(sender=admin)

    # Check that only the collects are paused
    scenario.verify(~marketplace.data.swaps_paused)
    scenario.verify(marketplace.data.collects_paused)

    # Check that collecting is not allowed
    scenario += marketplace.collect(0).run(valid=False, sender=collector1, amount=sp.mutez(edition_price))

    # Check that swapping is still allowed
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Check that cancel swaps are still allowed
    scenario += marketplace.cancel_swap(0).run(sender=artist1)

    # Unpause the collects again
    scenario += marketplace.set_pause_collects(False).run(sender=admin)

    # Check that swapping and collecting is possible again
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=swapped_editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)
    scenario += marketplace.collect(2).run(sender=collector1, amount=sp.mutez(edition_price))
    scenario += marketplace.cancel_swap(2).run(sender=artist1)


@sp.add_test(name="Test swap failure conditions")
def test_swap_failure_conditions():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    artist2 = testEnvironment["artist2"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]

    # Mint an OBJKT
    editions = 1
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Trying to swap more editions than are available must fail
    edition_price = 1000000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions + 1,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Trying to swap an OBJKT for which one doesn't have any editions must fail,
    # even for the admin
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=admin)

    # Trying to swap with royalties higher than 25% must fail
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=251,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Cannot swap 0 items
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=0,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Successfully swap
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Check that the swap was added
    scenario.verify(marketplace.data.swaps.contains(0))
    scenario.verify(~marketplace.data.swaps.contains(1))
    scenario.verify(marketplace.data.counter == 1)

    # Second swap should now fail because all avaliable editions have beeen swapped
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(valid=False, sender=artist1)

    # Mint a multi edition from a second OBJKT
    editions = 10
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist2.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist2)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 153
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist2.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist2)

    # Fail to swap second objkt as second artist when too many editions
    edition_price = 12000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions + 10,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist2.address).run(valid=False, sender=artist2)

    # Successfully swap the second objkt
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist2.address).run(sender=artist2)

    # Check that the swap was added
    scenario.verify(marketplace.data.swaps.contains(0))
    scenario.verify(marketplace.data.swaps.contains(1))
    scenario.verify(~marketplace.data.swaps.contains(2))
    scenario.verify(marketplace.data.counter == 2)

    # Check that is not possible to swap the second objkt because all editions
    # were swapped before
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=1,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist2.address).run(valid=False, sender=artist2)


@sp.add_test(name="Test cancel swap failure conditions")
def test_cancel_swap_failure_conditions():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    admin = testEnvironment["admin"]
    artist1 = testEnvironment["artist1"]
    artist2 = testEnvironment["artist2"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]

    # Mint an OBJKT
    editions = 1
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Successfully swap
    edition_price = 10000
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Check that the swap was added
    scenario.verify(marketplace.data.swaps.contains(0))
    scenario.verify(~marketplace.data.swaps.contains(1))
    scenario.verify(marketplace.data.counter == 1)

    # Check that cancelling a nonexistent swap fails
    scenario += marketplace.cancel_swap(1535).run(valid=False, sender=artist1)

    # Check that cancelling someone elses swap fails
    scenario += marketplace.cancel_swap(0).run(valid=False, sender=artist2)

    # Check that even the admin cannot cancel the swap
    scenario += marketplace.cancel_swap(0).run(valid=False, sender=admin)

    # Check that cancelling own swap works
    scenario += marketplace.cancel_swap(0).run(sender=artist1)

    # Check that the swap is gone
    scenario.verify(~marketplace.data.swaps.contains(0))
    scenario.verify(~marketplace.data.swaps.contains(1))

    # Check that the swap counter is still incremented
    scenario.verify(marketplace.data.counter == 1)


@sp.add_test(name="Test collect swap failure conditions")
def test_collect_swap_failure_conditions():
    # Get the test environment
    testEnvironment = get_test_environment()
    scenario = testEnvironment["scenario"]
    artist1 = testEnvironment["artist1"]
    collector1 = testEnvironment["collector1"]
    objkt = testEnvironment["objkt"]
    minter = testEnvironment["minter"]
    marketplace = testEnvironment["marketplace"]

    # Mint an OBJKT
    editions = 1
    royalties = 100
    scenario += minter.mint_OBJKT(
        address=artist1.address,
        amount=editions,
        metadata=sp.pack("ipfs://fff"),
        royalties=royalties).run(sender=artist1)

    # Add the marketplace contract as an operator to be able to swap it
    objkt_id = 152
    scenario += objkt.update_operators([sp.variant("add_operator", sp.record(
        owner=artist1.address,
        operator=marketplace.address,
        token_id=objkt_id))]).run(sender=artist1)

    # Successfully swap
    edition_price = 100
    scenario += marketplace.swap(
        fa2=objkt.address,
        objkt_id=objkt_id,
        objkt_amount=editions,
        xtz_per_objkt=sp.mutez(edition_price),
        royalties=royalties,
        creator=artist1.address).run(sender=artist1)

    # Check that trying to collect a nonexistent swap fails
    scenario += marketplace.collect(100).run(valid=False, sender=collector1, amount=sp.mutez(edition_price))

    # Check that trying to collect own swap fails
    scenario += marketplace.collect(0).run(valid=False, sender=artist1, amount=sp.mutez(edition_price))

    # Check that providing the wrong tez amount fails
    scenario += marketplace.collect(0).run(valid=False, sender=collector1, amount=sp.mutez(edition_price + 1))

    # Collect the OBJKT
    scenario += marketplace.collect(0).run(sender=collector1, amount=sp.mutez(edition_price))

    # Check that the swap entry still exists
    scenario.verify(marketplace.data.swaps.contains(0))

    # Check that there are no edition left for that swap
    scenario.verify(marketplace.data.swaps[0].objkt_amount == 0)
    scenario.verify(marketplace.data.counter == 1)

    # Check that trying to collect the swap fails
    scenario += marketplace.collect(0).run(valid=False, sender=collector1, amount=sp.mutez(edition_price))
