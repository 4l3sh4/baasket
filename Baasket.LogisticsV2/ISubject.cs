namespace Baasket.LogisticsV2;

/// <summary>
/// Maintains a list of observers and broadcasts state transitions to them.
/// </summary>
public interface ISubject
{
    void Attach(IObserver observer);
    void Detach(IObserver observer);
    void Notify(CheckoutSessionState previousState);
}
