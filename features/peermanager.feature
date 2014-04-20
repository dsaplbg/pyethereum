@config @peermanager @wip
Feature: peer manager

  Scenario: add_peer
    Given peer data of (connection, ip, port)
    When add_peer is called with the given peer data
    Then connected_peers should contain the peer with the peer data

  Scenario: stop
    Given peer manager with connected peers
    When instrument each peer's `stop` method
    And the peer manager's `stop` method is called
    Then each peer's `stop` method is called once

  Scenario: get connected peer addresses
    Given connected peer addresses, with each item is (ip, port, node_id)
    And add the connected peer addresses to to `connected_peers`
    Then get_connected_peer_addresses will return the given peer addresses

  Scenario: add/get known peer address
    Given peer address of (ip, port, node_id)
    Given connected peer addresses, with each item is (ip, port, node_id)
    And add the connected peer addresses to to `connected_peers`
    When add_known_peer_address is called with the given peer address
    Then get_known_peer_addresses will contain the given peer address

