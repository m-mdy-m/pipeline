using Xunit;

namespace Demo.Tests;

public class CalcTests
{
    [Fact]
    public void Adds() => Assert.Equal(5, Demo.Calc.Add(2, 3));
}
