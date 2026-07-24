from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway import main, build_parser

def test_build_parser():
    parser = build_parser()
    assert parser.prog == "gateway"
    
    # Test with a single source
    args = parser.parse_args(["--source", "medin", "--limit", "5", "--dry-run"])
    assert args.source == "medin"
    assert args.limit == 5
    assert args.dry_run is True
    
    # Test with 'all' source
    args = parser.parse_args(["--source", "all"])
    assert args.source == "all"

@patch("gateway.get_summoner_main")
@patch("gateway.get_scribe_main")
@patch("gateway.get_indexer_main")
@patch("gateway.get_summoner_config_loader")
def test_main_single_source(
    mock_get_summoner_config_loader,
    mock_get_indexer_main,
    mock_get_scribe_main,
    mock_get_summoner_main,
    tmp_path: Path
):
    # Mock the sub-main functions
    mock_summoner = MagicMock(return_value=0)
    mock_scribe = MagicMock(return_value=0)
    mock_indexer = MagicMock(return_value=0)
    
    mock_get_summoner_main.return_value = mock_summoner
    mock_get_scribe_main.return_value = mock_scribe
    mock_get_indexer_main.return_value = mock_indexer
    
    # Run gateway with a single source
    with patch("sys.argv", ["gateway.py", "--source", "test-src", "--dry-run"]):
        rc = main()
        
    assert rc == 0
    # Check that each sub-tool was called once with the correct arguments
    mock_summoner.assert_called_once()
    args, _ = mock_summoner.call_args
    assert "--source" in args[0]
    assert "test-src" in args[0]
    assert "--dry-run" in args[0]
    
    mock_scribe.assert_called_once()
    mock_indexer.assert_called_once()

@patch("gateway.get_summoner_main")
@patch("gateway.get_scribe_main")
@patch("gateway.get_indexer_main")
@patch("gateway.get_summoner_config_loader")
def test_main_all_sources(
    mock_get_summoner_config_loader,
    mock_get_indexer_main,
    mock_get_scribe_main,
    mock_get_summoner_main,
    fixtures_dir: Path
):
    # Mock the sub-main functions
    mock_summoner = MagicMock(return_value=0)
    mock_scribe = MagicMock(return_value=0)
    mock_indexer = MagicMock(return_value=0)
    
    mock_get_summoner_main.return_value = mock_summoner
    mock_get_scribe_main.return_value = mock_scribe
    mock_get_indexer_main.return_value = mock_indexer
    
    # Mock config loader to return multiple active sources
    mock_config = MagicMock()
    # In sample_config.yaml there are 2 active sources: active_src and headless_src
    # plus 1 inactive: inactive_src
    mock_source1 = MagicMock()
    mock_source1.name = "src1"
    mock_source1.active = True
    
    mock_source2 = MagicMock()
    mock_source2.name = "src2"
    mock_source2.active = True
    
    mock_source3 = MagicMock()
    mock_source3.name = "src3"
    mock_source3.active = False
    
    mock_config.sources = [mock_source1, mock_source2, mock_source3]
    
    mock_load_config = MagicMock(return_value=mock_config)
    mock_get_summoner_config_loader.return_value = mock_load_config
    
    config_file = fixtures_dir / "sample_config.yaml"
    
    # Run gateway with --source all
    with patch("sys.argv", ["gateway.py", "--source", "all", "--config", str(config_file)]):
        rc = main()
        
    assert rc == 0
    # Each sub-tool should be called twice (for src1 and src2)
    assert mock_summoner.call_count == 2
    assert mock_scribe.call_count == 2
    assert mock_indexer.call_count == 2
    
    # Verify sources processed
    summoner_calls = [call[0][0] for call in mock_summoner.call_args_list]
    sources_processed = []
    for call_args in summoner_calls:
        # Find the index of --source and get the next element
        idx = call_args.index("--source")
        sources_processed.append(call_args[idx+1])
    
    assert "src1" in sources_processed
    assert "src2" in sources_processed
    assert "src3" not in sources_processed

@patch("gateway.get_summoner_main")
@patch("gateway.get_scribe_main")
@patch("gateway.get_indexer_main")
@patch("gateway.get_summoner_config_loader")
def test_main_failure_continues(
    mock_get_summoner_config_loader,
    mock_get_indexer_main,
    mock_get_scribe_main,
    mock_get_summoner_main,
    fixtures_dir: Path
):
    # Summoner fails for the first source
    mock_summoner = MagicMock(side_effect=[1, 0]) 
    mock_scribe = MagicMock(return_value=0)
    mock_indexer = MagicMock(return_value=0)
    
    mock_get_summoner_main.return_value = mock_summoner
    mock_get_scribe_main.return_value = mock_scribe
    mock_get_indexer_main.return_value = mock_indexer
    
    mock_config = MagicMock()
    mock_s1 = MagicMock(); mock_s1.name = "fail-src"; mock_s1.active = True
    mock_s2 = MagicMock(); mock_s2.name = "ok-src"; mock_s2.active = True
    mock_config.sources = [mock_s1, mock_s2]
    
    mock_load_config = MagicMock(return_value=mock_config)
    mock_get_summoner_config_loader.return_value = mock_load_config
    
    config_file = fixtures_dir / "sample_config.yaml"
    
    with patch("sys.argv", ["gateway.py", "--source", "all", "--config", str(config_file)]):
        rc = main()
        
    # Should have non-zero exit code because one failed
    assert rc != 0
    # But should have attempted both
    assert mock_summoner.call_count == 2
    # Scribe and Indexer should only be called for the second source
    assert mock_scribe.call_count == 1
    assert mock_indexer.call_count == 1
