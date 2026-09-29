use strict;
use warnings;
my ($in, $out) = @ARGV;
open my $fi, '<', $in or die "$in: $!";
open my $fo, '>', $out or die "$out: $!";
while (my $line = <$fi>) {
  if ($line !~ /^VERSION/) {
    $line =~ s{(\d+\.\d+)}{sprintf('%.3f', int($1 * 200 + 0.5) * 0.005)}ge;
  }
  print {$fo} $line;
}
close $fo;
close $fi;
