namespace Baasket.LogisticsV2;

/// <summary>
/// Reacts to state changes on a <see cref="CheckoutSession"/> subject.
/// Concrete observers (receipt generation, automated tracking, etc.) arrive in Step 2.
/// </summary>
public interface IObserver
{
    /// <param name="session">The checkout session whose state changed.</param>
    /// <param name="previousState">The state immediately before the transition.</param>
    void Update(CheckoutSession session, CheckoutSessionState previousState);
}
