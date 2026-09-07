// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract FaceVerification {
    struct Record {
        string sourceUrl;
        string recordHash;
        uint256 timestamp;
        address submitter;
    }
    Record[] public records;

    event RecordAdded(uint256 indexed id, string recordHash, string sourceUrl);

    function addRecord(string memory _sourceUrl, string memory _recordHash) public returns (uint256) {
        records.push(Record(_sourceUrl, _recordHash, block.timestamp, msg.sender));
        uint256 id = records.length - 1;
        emit RecordAdded(id, _recordHash, _sourceUrl);
        return id;
    }

    function getRecord(uint256 id) public view returns (Record memory) {
        return records[id];
    }

    function getRecordCount() public view returns (uint256) {
        return records.length;
    }
}
