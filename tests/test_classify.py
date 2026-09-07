import unittest

from tests.fixtures import classify


class ClassifyTests(unittest.TestCase):
    def test_games_and_vlc(self):
        self.assertEqual(classify('digger'), 'digger')
        self.assertEqual(classify('renamed', '/usr/local/lib/digger/digger'), 'digger')
        self.assertEqual(classify('java', '/bin/java', 'org.prismlauncher.EntryPoint'), 'minecraft')
        self.assertEqual(classify('StardewValley'), 'stardew_valley')
        self.assertEqual(classify('vlc'), 'vlc')
        self.assertIsNone(classify('steam'))
        self.assertIsNone(classify('java', '/bin/java', 'unrelated-java-app'))
